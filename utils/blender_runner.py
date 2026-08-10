import os
import subprocess
import tempfile
import textwrap


def _strip_markdown_fences(script_content: str) -> str:
    """Remove markdown code fences (```python ... ```) that the LLM sometimes
    wraps the bpy script in, otherwise Blender raises a SyntaxError on the
    ```python fence line."""
    import re
    lines = script_content.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Drop opening/closing fences: ```, ```python, ```py, ```bpy, etc.
        if re.match(r"^```+(\s*[a-zA-Z0-9_]+)?\s*$", stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _fix_common_llm_api_errors(script_content: str) -> str:
    """Heal a few well-known mistakes the base LLM makes in generated bpy
    scripts so rendering does not abort on the first call. These are deterministic
    text substitutions (no AST parsing needed)."""
    # bpy.ops.object.select_all has no 'ALL' action; it must be 'SELECT'.
    script_content = script_content.replace("action='ALL'", "action='SELECT'")
    script_content = script_content.replace('action="ALL"', 'action="SELECT"')
    return script_content


def run_blender_script(script_content, name, output_folder, brightness, blender_executable, save_obj=False, save_image=False):
    script_content = _strip_markdown_fences(script_content)
    script_content = _fix_common_llm_api_errors(script_content)
    indented_user_script = textwrap.indent(script_content, "    ")

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as temp_script:
        temp_script.write(
            "import bpy\nimport os\nimport traceback\n"
            "from mathutils import Vector\n"
            "from bpy_extras.object_utils import world_to_camera_view\n"
            "bpy.ops.object.select_all(action='SELECT')\n"
            "bpy.ops.object.delete()\n"
        )

        temp_script.write("# === user script ===\ntry:\n")
        temp_script.write(indented_user_script + "\n")
        temp_script.write(
            "except Exception as e:\n"
            "    print('[SCRIPT_ERROR]', e)\n"
            "    traceback.print_exc()\n"
        )

        temp_script.write(
            r"""
def _mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']


def _sync_material_viewport_colors():
    for mat in bpy.data.materials:
        try:
            if not mat.use_nodes:
                continue
            bsdf = mat.node_tree.nodes.get('Principled BSDF') if mat.node_tree else None
            if bsdf is None:
                continue
            rgba = bsdf.inputs['Base Color'].default_value
            alpha = rgba[3]
            if 'Alpha' in bsdf.inputs:
                alpha = bsdf.inputs['Alpha'].default_value
            mat.diffuse_color = (rgba[0], rgba[1], rgba[2], alpha)
        except Exception as e:
            print(f"[material_sync][WARN] {mat.name}: {e}")


def _world_bbox_corners():
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    corners = []
    for obj in _mesh_objects():
        eval_obj = obj.evaluated_get(depsgraph)
        for corner in eval_obj.bound_box:
            corners.append(eval_obj.matrix_world @ Vector(corner))
    return corners


def _bbox_center_and_size(corners):
    min_corner = Vector((min(p.x for p in corners), min(p.y for p in corners), min(p.z for p in corners)))
    max_corner = Vector((max(p.x for p in corners), max(p.y for p in corners), max(p.z for p in corners)))
    center = (min_corner + max_corner) * 0.5
    size = max_corner - min_corner
    return center, size


def _look_at_euler(camera_location, target):
    direction = (target - camera_location).normalized()
    return direction.to_track_quat('-Z', 'Y').to_euler()


def _camera_sees_all(scene, cam_obj, points, margin=0.02):
    bpy.context.view_layer.update()
    for point in points:
        ndc = world_to_camera_view(scene, cam_obj, point)
        if ndc.z <= 0:
            return False
        if ndc.x < margin or ndc.x > 1.0 - margin:
            return False
        if ndc.y < margin or ndc.y > 1.0 - margin:
            return False
    return True


def _fit_camera_to_points(scene, cam_obj, points, lens_min=8.0, lens_max=120.0):
    cam_obj.data.type = 'PERSP'
    cam_obj.data.sensor_fit = 'AUTO'
    cam_obj.data.clip_start = 0.0001
    cam_obj.data.clip_end = 1000.0
    low = lens_min
    high = lens_max
    cam_obj.data.lens = lens_min
    if not _camera_sees_all(scene, cam_obj, points, margin=0.02):
        return False
    for _ in range(24):
        mid = (low + high) * 0.5
        cam_obj.data.lens = mid
        if _camera_sees_all(scene, cam_obj, points, margin=0.02):
            low = mid
        else:
            high = mid
    cam_obj.data.lens = low
    return True


def _camera_positions_from_bbox(center, max_dim):
    distance_scale = 1.35
    for _ in range(20):
        half_extent = max_dim * distance_scale
        positions = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    positions.append(center + Vector((sx * half_extent, sy * half_extent, sz * half_extent)))
        yield distance_scale, positions
        distance_scale *= 1.25


try:
    bpy.context.view_layer.update()
    _sync_material_viewport_colors()
except Exception as e:
    print('[scene_prepare][ERROR]', e)
    traceback.print_exc()
"""
        )

        if save_obj:
            temp_script.write(
                f"""
try:
    bpy.ops.object.select_all(action='DESELECT')
    mesh_objs = _mesh_objects()
    if mesh_objs:
        for obj in mesh_objs:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.wm.obj_export(
            filepath=os.path.join(r'{output_folder}', '{name}.obj'),
            export_selected_objects=True
        )
    else:
        print('[OBJ_EXPORT][WARN] No MESH objects to export.')
except Exception as e:
    print('[OBJ_EXPORT][ERROR]', e)
    traceback.print_exc()
"""
            )

        if save_image:
            temp_script.write(
                f"""
try:
    scene = bpy.context.scene
    mesh_objs = _mesh_objects()
    if not mesh_objs:
        raise RuntimeError('No MESH objects present; cannot render object views.')

    bbox_corners = _world_bbox_corners()
    bbox_center, bbox_size = _bbox_center_and_size(bbox_corners)
    max_dim = max(bbox_size.x, bbox_size.y, bbox_size.z, 1e-4)

    print(f'[BBOX] center={{tuple(round(v, 6) for v in bbox_center)}} size={{tuple(round(v, 6) for v in bbox_size)}}')

    scene.render.engine = 'BLENDER_WORKBENCH'
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.studiolight_intensity = 0.4
    shading.show_shadows = False
    shading.shadow_intensity = 0.0
    shading.color_type = 'MATERIAL'

    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100

    success_scale = None
    cameras = []
    for scale, candidate_positions in _camera_positions_from_bbox(bbox_center, max_dim):
        trial_cameras = []
        ok = True
        for index, location in enumerate(candidate_positions, start=1):
            camera_data = bpy.data.cameras.new(f'Camera_{{index}}')
            cam_obj = bpy.data.objects.new(f'Camera_{{index}}', camera_data)
            scene.collection.objects.link(cam_obj)
            scene.camera = cam_obj
            cam_obj.location = location
            cam_obj.data.clip_start = 0.0001
            cam_obj.data.clip_end = 1000.0
            cam_obj.rotation_euler = _look_at_euler(cam_obj.location, bbox_center)
            bpy.context.view_layer.update()
            if not _fit_camera_to_points(scene, cam_obj, bbox_corners):
                ok = False
            trial_cameras.append(cam_obj)
            if not ok:
                break
        if ok:
            success_scale = scale
            cameras = trial_cameras
            break
        for cam_obj in trial_cameras:
            bpy.data.objects.remove(cam_obj, do_unlink=True)

    if not cameras:
        raise RuntimeError('Failed to fit cameras to bbox after expanding camera cube.')

    print(f'[CAMERA_CUBE] distance_scale={{success_scale}}')
    for index, cam_obj in enumerate(cameras, start=1):
        scene.camera = cam_obj
        scene.render.filepath = os.path.join(r'{output_folder}', f'{name}_view{{index}}.png')
        print(f'[RENDER] view={{index}} location={{tuple(round(v, 6) for v in cam_obj.location)}} lens={{round(cam_obj.data.lens, 4)}}')
        bpy.ops.render.render(write_still=True)
except Exception as e:
    print('[RENDER][ERROR]', e)
    traceback.print_exc()
"""
            )

        script_path = temp_script.name

    # Run Blender headless. `--background` starts without UI; we intentionally do
    # NOT pass `--noaudio` because Blender 4.x no longer honours that flag in this
    # position and treats it as a file path, producing
    # "Cannot read file ... --noaudio". Headless background mode does not need audio.
    command = [blender_executable, "--background", "--python", script_path]
    result = subprocess.run(command, capture_output=True, text=True)
    os.remove(script_path)

    stdout_content = result.stdout or ""
    stderr_content = result.stderr or ""
    combined_output = "\n".join(part for part in (stdout_content, stderr_content) if part)
    print(combined_output)

    error_markers = ("Traceback", "[SCRIPT_ERROR]", "[RENDER][ERROR]", "[OBJ_EXPORT][ERROR]")
    if any(marker in combined_output for marker in error_markers) or result.returncode != 0:
        return f"Code Error:\n{combined_output.strip()}"
    return None
