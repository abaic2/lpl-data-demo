# LoL 联赛数据分析中心 (Streamlit Demo)

基于 **Games of Legends (gol.gg)** 公开统计数据的职业联赛分析看板，支持 **LPL / LCK / LCP** 三大赛区切换。

- 战队榜：胜率 / 场均时长 / 击杀 / 推塔 / 边路偏好
- 选手榜：KDA / DPM / GPM / 参团率 / 15 分钟经济差
- 英雄榜：BP 率 / 胜率 / 强度四象限（英雄名已按官方 Data Dragon zh_CN 汉化）
- 赛季对比：同年各赛事核心指标横向对比

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

数据每 30 分钟自动缓存刷新。仅供学习演示，League of Legends 及 LPL/LCK/LCP 相关版权归 Riot Games 及各赛区版权方所有。
