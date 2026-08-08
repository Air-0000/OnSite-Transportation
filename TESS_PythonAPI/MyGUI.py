import os
from pathlib import Path
from PySide2.QtWidgets import QMainWindow, QPushButton, QGroupBox, QTextBrowser, QVBoxLayout
from PySide2.QtWidgets import QWidget, QDockWidget, QMenu, QMessageBox, QFileDialog
from PySide2.QtCore import Qt

from tessng import tessngIFace


class MyGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # 代表TESS NG 的接口
        self.iface = tessngIFace()
        # 代表TESS NG 的路网子接口
        self.netiface = self.iface.netInterface()
        # 代表TESS NG 的仿真子接口
        self.simuiface = self.iface.simuInterface()
        # 代表TESS NG 的界面子接口
        self.guiiface = self.iface.guiInterface()
        # 主窗体
        self.main_window = self.guiiface.mainWindow()

        # 创建自定义面板
        self._create_gui()
        # 关联按钮与槽函数
        self._create_connect()
        # 添加到主窗体
        self._add_to_main_window()

    def _create_gui(self) -> None:
        """创建自定义面板"""
        # 创建按钮
        self.btn_open_net = QPushButton("打开路网")
        self.btn_start_simu = QPushButton("开启仿真")
        self.btn_pause_simu = QPushButton("暂停仿真")
        self.btn_stop_simu = QPushButton("停止仿真")

        # 创建信息窗
        self.group_box = QGroupBox("信息窗")
        self.txt_message = QTextBrowser(self.group_box)

        # 创建纵向布局
        self.vertical_layout_2 = QVBoxLayout(self.group_box)
        self.vertical_layout_2.setSpacing(6)
        self.vertical_layout_2.setContentsMargins(11, 11, 11, 11)
        self.vertical_layout_2.setContentsMargins(1, -1, 1, -1)
        self.vertical_layout_2.addWidget(self.txt_message)

        # 创建纵向布局
        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setSpacing(6)
        self.vertical_layout.setContentsMargins(11, 11, 11, 11)
        self.vertical_layout.addWidget(self.btn_open_net)
        self.vertical_layout.addWidget(self.btn_start_simu)
        self.vertical_layout.addWidget(self.btn_pause_simu)
        self.vertical_layout.addWidget(self.btn_stop_simu)
        self.vertical_layout.addWidget(self.group_box)

        # 设置布局
        self.central_widget = QWidget(self)
        self.central_widget.setLayout(self.vertical_layout)

    def _create_connect(self) -> None:
        """关联按钮与槽函数"""
        self.btn_open_net.clicked.connect(self._open_net)
        self.btn_start_simu.clicked.connect(self._start_simu)
        self.btn_pause_simu.clicked.connect(self._pause_simu)
        self.btn_stop_simu.clicked.connect(self._stop_simu)

    def _add_to_main_window(self) -> None:
        """添加自定义面板到主窗体"""
        dock_widget = QDockWidget("自定义与TESS NG交互界面", self.main_window)
        dock_widget.setObjectName("mainDockWidget")
        dock_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock_widget.setAllowedAreas(Qt.LeftDockWidgetArea)
        dock_widget.setWidget(self.central_widget)
        self.guiiface.addDockWidgetToMainWindow(Qt.DockWidgetArea(1), dock_widget)

        # 增加菜单及菜单项
        menu_bar = self.guiiface.menuBar()
        menu = QMenu(menu_bar)
        menu_bar.addAction(menu.menuAction())
        menu.setTitle("范例菜单")
        action_ok = menu.addAction("范例菜单项")
        action_ok.setCheckable(True)
        action_ok.triggered.connect(self._print_ok)

    def _open_net(self) -> None:
        """打开路网"""
        if self.simuiface.isRunning():
            QMessageBox.warning(None, "提示信息", "请先停止仿真，再打开路网")
            return
        cust_suffix = "TESSNG Files (*.tess);;TESSNG Files (*.backup)"
        db_dir = os.fspath(Path(__file__).resolve().parent)
        selected_filter = "TESSNG Files (*.tess)"
        options = QFileDialog.Options(0)
        net_file_path, filtr = QFileDialog.getOpenFileName(self, "打开文件", db_dir, cust_suffix, selected_filter, options)
        if net_file_path:
            self.netiface.openNetFle(net_file_path)

    def _start_simu(self) -> None:
        """开启仿真"""
        if not self.simuiface.isRunning() or self.simuiface.isPausing():
            self.simuiface.startSimu()

    def _pause_simu(self) -> None:
        """暂停仿真"""
        if self.simuiface.isRunning():
            self.simuiface.pauseSimu()

    def _stop_simu(self) -> None:
        """停止仿真"""
        if self.simuiface.isRunning():
            self.simuiface.stopSimu()

    def _print_ok(self) -> None:
        """自定义按钮关联的槽函数"""
        QMessageBox.information(None, "提示信息", "is ok!")

    def show_run_info(self, run_info: str) -> None:
        """在自定义面板的信息窗上显示信息"""
        self.txt_message.clear()
        self.txt_message.setText(run_info)
