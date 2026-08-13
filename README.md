# OnSite-Transportation 🚚

竞赛运输调度方案：拓扑分模式调度算法、题目分类、咽喉动态治理与提交工具。

## 项目结构

| 目录 | 说明 |
|------|------|
| `TESS_PythonAPI/` | TESS 仿真平台 Python API 调度实现（主代码） |
| `TESS_TopologyAnalysis/` | 拓扑分析、路径规划验证与结果日志 |

## 核心思路

- **拓扑分模式调度**：按道路拓扑将题目分为 `generic` / `ringseg` / `optimized` 三种模式分别处理
- **咽喉动态治理**：对瓶颈路段（咽喉）进行动态管控，缓解拥堵
- **提交工具**：`pack_submit.py` 打包 + `upload_curl.py` 上传

## 快速开始

```bash
cd TESS_PythonAPI
pip install -r requirements.txt
python main.py          # 运行调度
python od_classify.py   # OD 分类
python pack_submit.py   # 打包提交
```

## 验证

`TESS_TopologyAnalysis/` 下的 `validate_*` 系列脚本与日志记录了各模式的验证结果（generic/optimized 多轮对比）。

> 更多细节见 `TESS_PythonAPI/README.md`。
