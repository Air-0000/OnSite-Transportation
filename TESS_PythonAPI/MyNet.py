from PySide2.QtCore import QPointF

from tessng import PyCustomerNet, tessngIFace, m2p, p2m, NetItemType, GraphicsItemPropName


# 用户插件子类，代表用户自定义与路网相关的实现逻辑，继承自MyCustomerNet
class MyNet(PyCustomerNet):
    def __init__(self):
        super().__init__()
        # 代表TESS NG 的接口
        self.iface = tessngIFace()
        # 代表TESS NG 的路网子接口
        self.netiface = self.iface.netInterface()
        # 代表TESS NG 的仿真子接口
        self.simuiface = self.iface.simuInterface()

    # 自定义方法：创建路网上的路段和连接段
    def create_network(self) -> None:
        # 创建第一条路段
        start_point = QPointF(m2p(-300), 0)
        end_point = QPointF(m2p(300), 0)
        link_points = [start_point, end_point]
        link1 = self.netiface.createLink(link_points, 7, "曹安公路")
        if link1 is not None:
            # 车道列表
            lanes = link1.lanes()
            # 打印该路段所有车道ID列表
            print("曹安公路车道ID列表：", [lane.id() for lane in lanes])
            # 在当前路段创建发车点
            dp = self.netiface.createDispatchPoint(link1)
            if dp is not None:
                # 设置发车间隔，含车型组成、时间间隔、发车数
                dp.addDispatchInterval(1, 2, 28)

        # 创建第二条路段
        start_point = QPointF(m2p(-300), m2p(-25))
        end_point = QPointF(m2p(300), m2p(-25))
        link_points = [start_point, end_point]
        link2 = self.netiface.createLink(link_points, 7, "次干道")
        if link2 is not None:
            # 在当前路段创建发车点
            dp = self.netiface.createDispatchPoint(link2)
            if dp is not None:
                # 设置发车间隔，含车型组成、时间间隔、发车数
                dp.addDispatchInterval(1, 3600, 3600)
            # 将外侧车道设为公交专用道
            lanes = link2.lanes()
            lane = lanes[0]
            lane.setLaneType("公交专用道")

        # 创建第三条路段
        start_point = QPointF(m2p(-300), m2p(25))
        end_point = QPointF(m2p(-150), m2p(25))
        link_points = [start_point, end_point]
        link3 = self.netiface.createLink(link_points, 3)
        if link3 is not None:
            # 在当前路段创建发车点
            dp = self.netiface.createDispatchPoint(link3)
            if dp is not None:
                # 设置发车间隔，含车型组成、时间间隔、发车数
                dp.addDispatchInterval(1, 3600, 3600)

        # 创建第四条路段
        start_point = QPointF(m2p(-50), m2p(25))
        end_point = QPointF(m2p(50), m2p(25))
        link_points = [start_point, end_point]
        link4 = self.netiface.createLink(link_points, 3)

        # 创建第五条路段
        start_point = QPointF(m2p(150), m2p(25))
        end_point = QPointF(m2p(300), m2p(25))
        link_points = [start_point, end_point]
        link5 = self.netiface.createLink(link_points, 3, "自定义限速路段")
        if link5 is not None:
            # 设置路段限速 km/h
            link5.setLimitSpeed(30)

        # 创建第六条路段
        start_point = QPointF(m2p(-300), m2p(50))
        end_point = QPointF(m2p(300), m2p(50))
        link_points = [start_point, end_point]
        link6 = self.netiface.createLink(link_points, 3, "动态发车路段")
        if link6 is not None:
            # 设置路段限速 km/h
            link6.setLimitSpeed(80)

        # 创建第七条路段
        start_point = QPointF(m2p(-300), m2p(75))
        end_point = QPointF(m2p(-250), m2p(75))
        link_points = [start_point, end_point]
        link7 = self.netiface.createLink(link_points, 3)
        if link7 is not None:
            # 设置路段限速 km/h
            link7.setLimitSpeed(80)

        # 创建第八条路段
        start_point = QPointF(m2p(-50), m2p(75))
        end_point = QPointF(m2p(300), m2p(75))
        link_points = [start_point, end_point]
        link8 = self.netiface.createLink(link_points, 3)
        if link8 is not None:
            # 设置路段限速 km/h
            link8.setLimitSpeed(80)

        # 创建第一条连接段
        if link3 is not None and link4 is not None:
            from_lane_numbers = [1, 2, 3]
            to_lane_numbers = [1, 2, 3]
            connector1 = self.netiface.createConnector(link3.id(), link4.id(), from_lane_numbers, to_lane_numbers, "连接段1", True)

        # 创建第二条连接段
        if link4 is not None and link5 is not None:
            from_lane_numbers = [1, 2, 3]
            to_lane_numbers = [1, 2, 3]
            connector2 = self.netiface.createConnector(link4.id(), link5.id(), from_lane_numbers, to_lane_numbers, "连接段2", True)

        # 创建第三条连接段
        if link7 is not None and link8 is not None:
            from_lane_numbers = [1, 2, 3]
            to_lane_numbers = [1, 2, 3]
            connector3 = self.netiface.createConnector(link7.id(), link8.id(), from_lane_numbers, to_lane_numbers, "动态发车连接段", True)

    # 重写父类方法：当加载路网后TESS NG 调用此方法
    def afterLoadNet(self) -> None:
        # 获取路段数
        count = self.netiface.linkCount()
        # 如果路网上没有路段，则调用自定义的创建路网的方法
        if count == 0:
            self.create_network()

        if self.netiface.linkCount() > 0:
            # 所有路段对象列表
            links = self.netiface.links()
            # ID等于1的路段
            link = self.netiface.findLink(1)
            if link is not None:
                # 路段中心线断点集
                link_points = link.centerBreakPoints()
                # print("一条路段中心线断点：", [(p.x(), p.y()) for p in link_points])
                # 路段的车道对象列表
                lanes = link.lanes()
                if lanes is not None and len(lanes) > 0:
                    # 第一条车道中心线断点
                    lane_points = lanes[0].centerBreakPoints()
                    # print("一条车道中心线断点：", [(p.x(), p.y()) for p in lane_points])
            # 所有连接段对象列表
            connectors = self.netiface.connectors()
            if len(connectors) > 0:
                # 第一条连接段的所有“车道连接”
                lane_connectors = connectors[0].laneConnectors()
                # 其中第一条“车道连接”
                lane_connector = lane_connectors[0]
                # "车道连接“断点集
                lane_connector_points = lane_connector.centerBreakPoints()
                # print("一条'车道连接'中心线断点：", [(p.x(), p.y()) for p in lane_connector_points])

    # 重写父类方法：是否允许用户对路网元素的绘制进行干预，如选择路段标签类型、确定绘制颜色等，本方法目的在于减少不必要的对python方法调用频次
    def isPermitForCustDraw(self) -> bool:
        """
        :return: 返回值，True表示允许用户对路网元素的绘制进行干预，False表示不允许用户对路网元素的绘制进行干预
        """
        # 获取当前路网文件名
        net_file_name = self.netiface.netFilePath()
        if "Temp" in net_file_name:
            return True
        else:
            return False

    # 重写父类方法：在绘制路网元素时被调用，确定用ID或名称，以及字体大小绘制标签，也可确定不绘制标签
    def ref_labelNameAndFont(self, itemType, itemId, ref_outPropName, ref_outFontSize) -> None:
        """
        :param itemType: NetItemType常量，代表不同类型路网元素
        :param itemId: 路网元素的ID
        :param ref_outPropName: GraphicsItemPropName枚举类型，None_表示不绘制，ID表示绘制ID，NAME表示绘制名称，影响路段和连接段的标签是否被绘制
        :param ref_outFontSize: 标签大小，单位：米。假设车道宽度是3.5米，如果ref_outFontSize.value等于7，绘制的标签大小占两个车道宽度
        """
        # 如果仿真正在进行，设置ref_outPropName.value等于GraphicsItemPropName.None_，路段和车道都不绘制标签
        if self.simuiface.isRunning():
            ref_outPropName.value = GraphicsItemPropName.None_
            return
        # 默认绘制ID
        ref_outPropName.value = GraphicsItemPropName.Id
        # 标签大小为6米
        ref_outFontSize.value = 6
        # 如果是连接段一律绘制名称
        if itemType == NetItemType.GConnectorType:
            ref_outPropName.value = GraphicsItemPropName.Name
        # 如果是路段，则根据ID判断是否绘制名称
        elif itemType == NetItemType.GLinkType:
            if itemId == 1 or itemId == 5 or itemId == 6:
                ref_outPropName.value = GraphicsItemPropName.Name

    # 重写父类方法：是否绘制车道中心线
    def isDrawLaneCenterLine(self, lane_id: int) -> bool:
        """
        :param lane_id: 车道ID
        :return: 是否绘制车道中心线，True表示绘制，False表示不绘制
        """
        return True

    # 重写父类方法：是否绘制路段中心线
    def isDrawLinkCenterLine(self, link_id: int) -> bool:
        """
        :param link_id: 路段ID
        :return: 是否绘制路段中心线，True表示绘制，False表示不绘制
        """
        return link_id != 1
