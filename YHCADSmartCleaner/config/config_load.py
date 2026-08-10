import sys
import ctypes
import importlib
import os
import json

def init_ncti_config():
    jsonData = get_system_config_json()
    dllpath = jsonData["dllPath"]
    addKernelPath = jsonData["addKernelPath"]
    loadDLLs = jsonData["loadDLL"]
    #add dll path
    if False == os.path.isabs(dllpath):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dllpath =  current_dir+"/"+dllpath
    try:
        sys.path.insert(0, dllpath)
        for ker in addKernelPath:
            api_path = dllpath + "/" + ker
            os.add_dll_directory(api_path)
        #add dll
        for loadDll in loadDLLs:
            addDllPath = dllpath + "/" + loadDll
            ctypes.CDLL(addDllPath)
        #init ncti_python
        NCTI = importlib.import_module("ncti_python")
        NCTI.Init(dllpath)
        return NCTI
    except:
        print("System path error or loading dll failure!")
        return None

def get_system_config_json():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        jsonfile = current_dir + '/' + "system_config.json"
        with open(jsonfile, 'r',encoding='utf-8') as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        print("文件未找到")
        return ""
    except json.JSONDecodeError:
        print("JSON 文件格式错误")
        return ""
    
global_scope = {}
NCTI = init_ncti_config()
if None != NCTI:
    global_scope["NCTI"] = NCTI
    global_scope["doc"] = NCTI.Document()
