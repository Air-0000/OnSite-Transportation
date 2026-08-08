import os
from MyPlugin import MyPlugin

if __name__ == "__main__":
    config = {
        "__netfilepath": "Scene/gangqu1.tess",  # TODO 路网文件路径
        "__workspace": os.path.join(os.getcwd(), "WorkSpace"),  # 工作空间路径
        "__simuafterload": True,  # 加载路网后是否自动开启仿真
        "__custsimubysteps": False,
    }
    my_tess_plugin = MyPlugin(config)
    my_tess_plugin.build()
