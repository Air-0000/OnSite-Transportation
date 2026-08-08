import os
from PySide2.QtWidgets import QApplication

from tessng import TessPlugin, TessngFactory
from MyGUI import MyGUI
from MyNet import MyNet
from MySimulator import MySimulator


# 用户插件，继承自TessPlugin
class MyPlugin(TessPlugin):
    def __init__(self, config: dict):
        super().__init__()
        # 配置
        self.config: dict = config
        # 自定义界面
        self.my_gui = None
        # 自定义路网控制逻辑
        self.my_net = None
        # 自定义仿真控制逻辑
        self.my_simulator = None

    # 启动TESS NG 窗体
    def build(self) -> None:
        # 创建工作空间文件夹
        default_workspace: str = os.path.join(os.getcwd(), "WorkSpace")
        workspace: str = self.config.get("__workspace", default_workspace)
        os.makedirs(workspace, exist_ok=True)

        # 创建TESS NG 对象
        app = QApplication()
        factory = TessngFactory()
        tessng = factory.build(self, self.config)
        if tessng is not None:
            app.exec_()

    # 重写父类方法：在TESS NG 工厂类创建TESS NG 对象时调用
    def init(self) -> None:
        # 自定义界面
        self.my_gui = MyGUI()
        # 自定义路网控制逻辑
        self.my_net = MyNet()
        # 自定义仿真控制逻辑
        self.my_simulator = MySimulator()

        # 关联信号和槽函数
        self.my_simulator.showRunInfo.connect(self.my_gui.show_run_info)

    # 重写父类方法：返回插件路网子接口，此方法由TESS NG 调用
    def customerNet(self):
        return self.my_net

    # 重写父类方法：返回插件仿真子接口，此方法由TESS NG 调用
    def customerSimulator(self):
        return self.my_simulator
