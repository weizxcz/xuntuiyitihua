import os
import shutil
import re
import numpy as np
import sys
import ctypes
import importlib
import faiss
from create_image_database import ImageKnowledgeBase
from tqdm import tqdm

class Stp2images(object):
    def __init__(self):
        Ncti_api_path = r"D:\软件\biaozhuruanjian\OCC"
        os.add_dll_directory(Ncti_api_path)
        dllpath = r"D:\软件\biaozhuruanjian"
        sys.path.insert(0, dllpath)
        ctypes.CDLL(dllpath + "/ncti_command.dll")
        ctypes.CDLL(dllpath + "/ncti_occ_plugin.dll")
        ctypes.CDLL(dllpath + "/ncti_render_vulkan.dll")
        self.NCTI = importlib.import_module("ncti_python")
        self.NCTI.Init(dllpath)
          # 保留在装配结构
        # view = self.NCTI.View(self.doc.ID)
        # view.CreateWindow()
        # view.SetVisualMode(1, 1, 0)
        # view.SetAxisVis(0)
        self.cameras = [self.NCTI.Vector(0.7071067811865476, 0.7071067811865475, 0.2)]

    def save_view_as_image(self,doc,view,curGroup, group,filename):
        """ Save the current view from display to an image file. """
        solid_list = group.GetAllSubObject(curGroup)
        view.ShowOnly(solid_list)
        view.Zoom(solid_list)
        for i in range(len(self.cameras)):
            view.Straighten(self.cameras[i])
            doc.Update()
            doc.SaveImage(filename)
    

    def setup_and_save_images(self,step_file, output_dir):
        doc = self.NCTI.Document()
        doc.New("OCC", "DCM", "GMSH")
        doc.SetImportAssemelFile(1)
        view = self.NCTI.View(doc.ID)
        view.CreateWindow()
        view.SetVisualMode(1,1, 0)
        view.SetAxisVis(0)
        doc.RunCommand("cmd_ncti_import_file", step_file, 2)
        group = self.NCTI.RootGroup(doc)
        root_group = group.GetCurSubGroup()[0]
        cad_part_name = os.path.splitext(os.path.basename(step_file))[0]
        output_filename = os.path.join(output_dir, f"{cad_part_name}.png")
        self.save_view_as_image(doc,view,root_group,group,output_filename)
        doc.Close()


    def batch_process_step_files(self,step_folder, output_folder):
        step_files = [os.path.join(step_folder, f) for f in os.listdir(step_folder) if
                    f.endswith('.step') or f.endswith('.stp') or f.endswith('.STEP')]

        for step_file in step_files:
            # setup_and_save_images(step_file, output_folder)
            try:
                self.setup_and_save_images(step_file, output_folder)
            except:
                pass

    def folder_process_step_files(self,output_folder_images, output_folder_group_images):
        images_files = os.listdir(output_folder_images)
        for image_file in images_files:
            image_path = os.path.join(output_folder_images, image_file)
            image_name = image_file.split('_')[0]
            image_name = re.sub(r'\d+$', '', image_name)
            group_image_path = os.path.join(output_folder_group_images, image_name)
            if not os.path.exists(group_image_path):
                os.makedirs(group_image_path)
            shutil.copy(image_path, group_image_path)

    def folder_process_step_files_drop_duplicates(self,kb,output_folder_images, output_folder_group_images):
        pcb_files = os.listdir(output_folder_images)
        for i,pcb in enumerate(pcb_files):
            # if '机箱测试' in pcb:
            #     continue
            image_dir = os.path.join(output_folder_images,pcb)
            images_files = os.listdir(image_dir)
            for j,image_file in enumerate(images_files):
                image_path = os.path.join(image_dir, image_file)
                query_features = kb.extract_features(image_path)
                query_features = np.array([query_features]).astype('float32')
                if i==0 and j ==0:
                    index = faiss.IndexFlatIP(query_features.shape[1])  # 使用内积相似度
                    faiss.normalize_L2(query_features)  # 归一化特征向量
                    index.add(query_features)
                else:
                    faiss.normalize_L2(query_features)
                    similarities, indices = index.search(query_features, 1)
                    if similarities[0]>0.998:
                        continue
                    index.add(query_features)
                    if '_' in image_file:
                        image_name = image_file.split('_')[0]
                    else:
                        image_name = image_file.split('.')[0]
                    image_name = re.sub(r'\d+$', '', image_name)
                    group_image_path = os.path.join(output_folder_group_images, image_name)
                    if not os.path.exists(group_image_path):
                        os.makedirs(group_image_path)
                    file_amount_list = os.listdir(group_image_path)
                    file_amount = len(file_amount_list)
                    new_image_name = f'{image_name}_{file_amount}.png'
                    new_group_image_path = os.path.join(group_image_path,new_image_name)
                    shutil.copy(image_path, new_group_image_path)


if __name__ == '__main__':
    # current_dir = os.getcwd()
    current_file_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file_path)
    main_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(main_dir,'data')

    step_data_dir = r'E:\recongnize\标注数据批量导出\ncti2step_data\公司标注\第四批'
    picture_out_floder = r'E:\recongnize\标注数据批量导出\ncti2step_data\公司标注\第四批图片'
    # picture_out_floder = os.path.join(data_dir,'picture_data')
    output_folder_group_images = os.path.join(data_dir,"picture_group_data")
    os.makedirs(output_folder_group_images, exist_ok=True)
    data_list = os.listdir(step_data_dir)
    output_folder_exist_list = os.listdir(picture_out_floder)
    kb = ImageKnowledgeBase()
    main_class = Stp2images()
    for file in tqdm(data_list):#[53:]
        if file.endswith('xlsx'):
            continue
        step_folder = os.path.join(step_data_dir, file)
        output_folder = os.path.join(picture_out_floder, file)
        if file in output_folder_exist_list:
            continue
        os.makedirs(output_folder, exist_ok=True)
        try:
            main_class.batch_process_step_files(step_folder,output_folder)
        except:
            pass

    # main_class.folder_process_step_files_drop_duplicates(kb,picture_out_floder, output_folder_group_images)


    