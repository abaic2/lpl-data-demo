# -*- coding: utf-8 -*-
"""
LPL 数据分析中心 · Streamlit Demo
数据来源: Games of Legends (gol.gg) 公开统计页面
"""
import re
import socket
import urllib.parse
import urllib.request

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_option_menu import option_menu

socket.setdefaulttimeout(30)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LPL-Demo/1.0"}
BASE = "https://gol.gg"

# ============================================================
# 数据层
# ============================================================

def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8", "replace")


def _cell_text(html):
    t = re.sub(r"<[^>]+>", " ", html)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def _parse_rows(html, link_kw):
    """解析 gol.gg 列表页主数据表, 返回 (表头list, 行list[list[str]])"""
    th = [x.strip() for x in re.findall(r"<th[^>]*>([^<]*)</th>", html) if x.strip()]
    rows = re.findall(
        r"<tr[^>]*>((?:(?!</tr>).)*" + link_kw + r"(?:(?!</tr>).)*)</tr>", html, re.S
    )
    out = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if not cells:
            continue
        out.append([_cell_text(c) for c in cells])
    return th, out


@st.cache_data(ttl=1800, show_spinner="正在从 gol.gg 拉取 LPL 赛事列表 ...")
def list_lpl_tournaments():
    html = _get(BASE + "/players/list/season-ALL/split-ALL/tournament-ALL/")
    m = re.search(r"<select id='cbtournament'.*?</select>", html, re.S)
    if not m:
        return []
    opts = re.findall(r"<option[^>]*value='([^']+)'[^>]*>\s*([^<]+?)\s*</option>", m.group(0))
    names = [v.strip() for v, n in opts if n.strip().startswith("LPL ")]
    return names


@st.cache_data(ttl=1800, show_spinner="正在拉取选手数据 ...")
def fetch_players(tournament):
    tok = urllib.parse.quote(tournament)
    html = _get(BASE + "/players/list/season-ALL/split-ALL/tournament-%s/" % tok)
    th, rows = _parse_rows(html, "player-stats")
    # 按探测结果固定列映射
    cols = ["选手", "赛区", "场次", "胜率", "KDA", "场均击杀", "场均死亡", "场均助攻",
            "CSM", "GPM", "参团率", "伤害占比", "经济占比", "分均插眼", "DPM",
            "VSPM", "WPM", "WCPM", "VWPM", "GD@15", "CSD@15", "XPD@15",
            "一血率", "一血被杀率", "五杀", "单杀"]
    data = []
    for r in rows:
        if len(r) < 25:
            continue
        d = dict(zip(cols, r))
        data.append(d)
    df = pd.DataFrame(data)
    for c in ["场次"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["胜率", "参团率", "伤害占比", "经济占比", "一血率", "一血被杀率"]:
        df[c + "_v"] = pd.to_numeric(df[c].str.rstrip("%"), errors="coerce")
    for c in ["KDA", "场均击杀", "场均死亡", "场均助攻", "CSM", "GPM", "DPM", "GD@15", "五杀", "单杀"]:
        df[c + "_v"] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["场次"])
    return df


@st.cache_data(ttl=1800, show_spinner="正在拉取战队数据 ...")
def fetch_teams(tournament):
    tok = urllib.parse.quote(tournament)
    html = _get(BASE + "/teams/list/season-ALL/split-ALL/tournament-%s/" % tok)
    th, rows = _parse_rows(html, "team-stats")
    cols = ["战队", "赛季", "赛区", "场次", "胜率", "K:D", "GPM", "经济差", "场均时长",
            "首选边率", "蓝方率", "场均击杀", "场均死亡", "场均推塔", "场均被推塔"]
    data = []
    for r in rows:
        if len(r) < 15:
            continue
        data.append(dict(zip(cols, r)))
    df = pd.DataFrame(data)
    df["场次_v"] = pd.to_numeric(df["场次"], errors="coerce")
    df["胜率_v"] = pd.to_numeric(df["胜率"].str.rstrip("%"), errors="coerce")
    for c in ["K:D", "GPM", "场均击杀", "场均死亡", "场均推塔", "场均被推塔", "蓝方率"]:
        df[c + "_v"] = pd.to_numeric(df[c], errors="coerce")

    def _dur(s):
        m = re.match(r"(\d+):(\d+)", s or "")
        return int(m.group(1)) + int(m.group(2)) / 60 if m else None

    df["时长_min"] = df["场均时长"].map(_dur)
    df = df.dropna(subset=["场次_v"])
    # 战队全名修正 (gol.gg 去掉了撇号)
    fix = {"Anyone s Legend": "Anyone's Legend", "Bilibili Gaming": "Bilibili Gaming",
           "Top Esports": "Top Esports", "FunPlus Phoenix": "FunPlus Phoenix",
           "Ninjas in Pyjamas": "Ninjas in Pyjamas", "Weibo Gaming": "Weibo Gaming"}
    df["战队"] = df["战队"].replace(fix)
    return df


@st.cache_data(ttl=1800, show_spinner="正在拉取英雄数据 ...")
def fetch_champions(tournament):
    tok = urllib.parse.quote(tournament)
    html = _get(BASE + "/champion/list/season-ALL/split-ALL/tournament-%s/" % tok)
    th, rows = _parse_rows(html, "champion-stats")
    cols = ["英雄", "选取", "禁用", "优先级", "胜场", "败场", "胜率", "KDA",
            "BT", "RP", "BP率", "场均时长", "CSM", "DPM", "GPM"]
    data = []
    for r in rows:
        if len(r) < 15:
            continue
        data.append(dict(zip(cols, r)))
    df = pd.DataFrame(data)
    for c in ["选取", "禁用", "胜场", "败场"]:
        df[c + "_v"] = pd.to_numeric(df[c], errors="coerce")
    for c in ["优先级", "胜率", "BP率"]:
        df[c + "_v"] = pd.to_numeric(df[c].str.rstrip("%"), errors="coerce")
    for c in ["KDA", "CSM", "DPM", "GPM"]:
        df[c + "_v"] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["选取_v"])
    return df


# ============================================================
# 样式
# ============================================================
CSS = """
<style>
/* 主区域 */
.stApp { background: #0b0e14; }
.stApp > header { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1200px; }
h1, h2, h3, h4, .stMarkdown { color: #e6e9f0; }
[data-testid="stMetricValue"] { color: #ff8f93; }

/* 侧边栏: 根节点双写兼容新旧版本 */
section[data-testid="stSidebar"], div[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #12060a 0%, #1a0e14 55%, #241018 100%) !important;
  border-right: 1px solid #2c1a22;
}
section[data-testid="stSidebar"] > div, div[data-testid="stSidebar"] > div,
div[data-testid="stSidebarContent"],
div[data-testid="stSidebar"] [data-testid="stSidebarContent"],
div[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  background: transparent !important;
}
section[data-testid="stSidebar"] *, div[data-testid="stSidebar"] * { color: #FFFFFF !important; }
section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small,
div[data-testid="stSidebar"] .stCaption, div[data-testid="stSidebar"] small { color: #d9a7ad !important; }
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #FFFFFF !important; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] [data-baseweb="select"] * { color: #22304F !important; }
section[data-testid="stSidebar"] .stButton > button,
div[data-testid="stSidebar"] .stButton > button {
  background: rgba(255,255,255,.08); border: 1px solid rgba(229,72,77,.45);
  color: #FFFFFF !important; border-radius: 11px; white-space: normal; line-height: 1.5;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
div[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #e5484d, #ff8f93); color: #1a0508 !important;
  border: none; font-weight: 700;
}

/* 卡片化容器 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #131824; border: 1px solid #242d42; border-radius: 14px;
}
div[data-testid="stDataFrame"] { border: 1px solid #242d42; border-radius: 10px; }
</style>
"""

MENU_STYLES = {
    "container": {"padding": "10px 8px", "background-color": "#1c0e14",
                  "border-radius": "14px", "border": "1px solid rgba(229,72,77,0.35)"},
    "icon": {"color": "#ff8f93", "font-size": "16px"},
    "nav-link": {"font-size": "15px", "color": "#FFFFFF", "font-weight": "600",
                 "margin": "4px 0", "padding": "10px 16px", "border-radius": "12px",
                 "--hover-color": "rgba(229,72,77,0.22)", "border": "1px solid transparent"},
    "nav-link-selected": {
        "background": "linear-gradient(90deg, rgba(229,72,77,0.40), rgba(229,72,77,0.12))",
        "border": "1px solid rgba(229,72,77,0.75)", "color": "#ffd9db",
        "font-weight": "800", "border-left": "4px solid #e5484d"},
}

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Microsoft YaHei, Segoe UI, sans-serif", color="#c8cfdd", size=13),
    margin=dict(l=10, r=10, t=42, b=10),
    height=360,
)
RED, GOLD, BLUE, GREEN = "#e5484d", "#e8b64c", "#4c8de5", "#46c07a"


def style_fig(fig, height=360):
    fig.update_layout(**{**PLOTLY_LAYOUT, "height": height})
    fig.update_xaxes(gridcolor="#242d42", zerolinecolor="#242d42")
    fig.update_yaxes(gridcolor="#242d42", zerolinecolor="#242d42")
    return fig


def hero(title, sub):
    st.markdown(
        f"""
        <div style="background:linear-gradient(120deg,#1a2132,#131824 55%,#241018);
             border:1px solid #242d42;border-radius:14px;padding:22px 26px;margin-bottom:18px;">
          <div style="font-size:24px;font-weight:800;letter-spacing:1px;color:#ffffff;">
            LPL 数据分析中心
            <span style="font-size:12px;font-weight:400;color:#e8b64c;
              border:1px solid rgba(232,182,76,.4);border-radius:20px;padding:2px 10px;
              margin-left:10px;vertical-align:middle;">真实数据 · gol.gg</span>
          </div>
          <div style="color:#8a93a8;font-size:13px;margin-top:6px;">{sub}</div>
          <div style="color:#5c667e;font-size:11px;margin-top:4px;">{title}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 页面
# ============================================================

def page_overview(tour, teams, players, champs):
    hero(tour, "总览 · 本届 LPL 赛事核心指标与头部榜单")
    n_games = int(teams["场次_v"].sum() // 2) if len(teams) else 0
    avg_dur = teams["时长_min"].mean() if len(teams) else 0
    avg_kill = (teams["场均击杀_v"].mean() + teams["场均死亡_v"].mean()) / 2 if len(teams) else 0
    champ_games = int(champs["选取_v"].sum()) if len(champs) else 0

    c = st.columns(4)
    c[0].metric("参赛战队", f"{len(teams)} 支", f"共 {n_games} 场", border=True)
    c[1].metric("场均时长", f"{int(avg_dur)}:{int(avg_dur*60%60):02d}", border=True)
    c[2].metric("场均击杀(单队)", f"{avg_kill:.1f}", border=True)
    c[3].metric("英雄选取总人次", f"{champ_games}", f"登场英雄 {len(champs)} 个", border=True)

    left, right = st.columns(2)
    with left:
        st.markdown("##### 战队胜率榜")
        d = teams.sort_values("胜率_v", ascending=False).head(10)
        fig = px.bar(d, x="胜率_v", y="战队", orientation="h",
                     color="胜率_v", color_continuous_scale=["#3a1a20", "#e5484d"],
                     text="胜率")
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition="outside", textfont_color="#e8b64c")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 420), width='stretch')
    with right:
        st.markdown("##### 选手 KDA 榜 (场次 ≥ 10)")
        d = players[players["场次"] >= 10].sort_values("KDA_v", ascending=False).head(10)
        fig = px.bar(d, x="KDA_v", y="选手", orientation="h",
                     color="KDA_v", color_continuous_scale=["#241a08", "#e8b64c"],
                     text="KDA", hover_data=["场次", "GPM"])
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition="outside", textfont_color="#ff8f93")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 420), width='stretch')

    st.markdown("##### 英雄优先级 TOP 12 (BP率 = (选取+禁用)/总场次)")
    d = champs.sort_values("BP率_v", ascending=False).head(12)
    fig = go.Figure()
    fig.add_bar(x=d["英雄"], y=d["选取_v"], name="选取", marker_color=RED)
    fig.add_bar(x=d["英雄"], y=d["禁用_v"], name="禁用", marker_color="#8a5cf6")
    fig.update_layout(barmode="group")
    st.plotly_chart(style_fig(fig, 340), width='stretch')


def page_teams(teams):
    hero("战队页 · 战队榜单与风格对比", "战队页 · 数据口径: 本届赛事常规赛")
    st.markdown("##### 战队数据总表")
    show = teams[["战队", "场次", "胜率", "K:D", "场均时长", "场均击杀", "场均死亡",
                  "场均推塔", "首选边率", "蓝方率"]].copy()
    show.columns = ["战队", "场次", "胜率", "K:D", "场均时长", "场均击杀", "场均死亡",
                    "场均推塔", "首抢率", "蓝方率"]
    st.dataframe(show, hide_index=True, width='stretch')

    left, right = st.columns(2)
    with left:
        st.markdown("##### 进攻风格: 场均击杀 vs 场均时长")
        fig = px.scatter(teams, x="时长_min", y="场均击杀_v", text="战队",
                         size="场次_v", color="胜率_v",
                         color_continuous_scale=["#46c07a", "#e8b64c", "#e5484d"])
        fig.update_traces(textposition="top center", textfont_size=10)
        st.plotly_chart(style_fig(fig, 400), width='stretch')
    with right:
        st.markdown("##### 运营风格: 场均推塔 vs 场均死亡")
        fig = px.scatter(teams, x="场均死亡_v", y="场均推塔_v", text="战队",
                         size="场次_v", color="GPM_v",
                         color_continuous_scale=["#132743", "#4c8de5"])
        fig.update_traces(textposition="top center", textfont_size=10)
        st.plotly_chart(style_fig(fig, 400), width='stretch')


def page_players(players):
    hero("选手页 · 选手榜单与输出能力", "选手页 · 覆盖本届所有登场选手")
    st.markdown("##### 选手数据总表 (可排序/搜索)")
    show = players[["选手", "赛区", "场次", "胜率", "KDA", "场均击杀", "场均死亡",
                    "场均助攻", "CSM", "GPM", "参团率", "DPM", "GD@15", "五杀", "单杀"]].copy()
    st.dataframe(show, hide_index=True, width='stretch', height=460)

    left, right = st.columns(2)
    with left:
        st.markdown("##### 输出机器: DPM TOP 12 (场次 ≥ 10)")
        d = players[players["场次"] >= 10].sort_values("DPM_v", ascending=False).head(12)
        fig = px.bar(d, x="DPM_v", y="选手", orientation="h", color="DPM_v",
                     color_continuous_scale=["#3a1a20", "#e5484d"], text="DPM",
                     hover_data=["场次", "KDA", "伤害占比"])
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition="outside", textfont_color="#ff8f93")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 400), width='stretch')
    with right:
        st.markdown("##### KDA vs 分均伤害 (场次 ≥ 10)")
        d = players[players["场次"] >= 10]
        fig = px.scatter(d, x="DPM_v", y="KDA_v", text="选手", size="场次",
                         color="胜率_v", color_continuous_scale=["#46c07a", "#e8b64c", "#e5484d"],
                         hover_data=["GPM", "参团率"])
        fig.update_traces(textposition="top center", textfont_size=9)
        st.plotly_chart(style_fig(fig, 400), width='stretch')

    st.markdown("##### 对线统治力: GD@15 (15 分钟经济差) TOP 10 (场次 ≥ 8)")
    d = players[players["场次"] >= 8].dropna(subset=["GD@15_v"]).sort_values("GD@15_v", ascending=False).head(10)
    fig = px.bar(d, x="GD@15_v", y="选手", orientation="h", color="GD@15_v",
                 color_continuous_scale=["#241a08", "#e8b64c"], text="GD@15")
    fig.update_yaxes(autorange="reversed")
    fig.update_traces(textposition="outside", textfont_color="#e8b64c")
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(style_fig(fig, 360), width='stretch')


def page_champions(champs, teams):
    hero("英雄页 · 英雄 BP 与强度分析", "英雄页 · 选取/禁用/胜率全覆盖")
    n_total = int(champs["选取_v"].sum() + champs["禁用_v"].sum())
    st.markdown(f"##### 英雄数据总表 (共 {len(champs)} 个英雄登场, BP 总人次 {n_total})")
    show = champs[["英雄", "选取", "禁用", "BP率", "胜率", "KDA", "DPM", "CSM"]].copy()
    st.dataframe(show, hide_index=True, width='stretch', height=440)

    left, right = st.columns(2)
    with left:
        st.markdown("##### 强度四象限: 胜率 vs BP率")
        fig = px.scatter(champs, x="BP率_v", y="胜率_v", text="英雄",
                         size="选取_v", color="胜率_v",
                         color_continuous_scale=["#5c667e", "#4c8de5", "#e5484d"],
                         hover_data=["选取", "禁用", "KDA"])
        fig.add_hline(y=50, line_dash="dot", line_color="#39435c")
        fig.update_traces(textposition="top center", textfont_size=8)
        st.plotly_chart(style_fig(fig, 430), width='stretch')
    with right:
        st.markdown("##### 禁用榜 TOP 12")
        d = champs.sort_values("禁用_v", ascending=False).head(12)
        fig = px.bar(d, x="禁用_v", y="英雄", orientation="h", color="禁用_v",
                     color_continuous_scale=["#1f1533", "#8a5cf6"], text="禁用")
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition="outside", textfont_color="#c3a9f5")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 430), width='stretch')


def page_compare(tours, tour):
    hero("赛季对比页 · 同年各 Split 横向对比", "赛季对比页 · 拉取多届数据自动对比")
    splits = [t for t in tours if re.search(r"Split \d$", t)] or tours
    frames = {}
    with st.status("正在拉取各 Split 战队数据 ...", expanded=True) as s:
        for t in splits:
            st.write("→ " + t)
            frames[t] = fetch_teams(t)
        s.update(label="拉取完成", state="complete")
    rows = []
    for t, df in frames.items():
        if not len(df):
            continue
        rows.append({
            "赛事": t.replace("LPL 2026 ", ""),
            "战队数": len(df),
            "总场次": int(df["场次_v"].sum() // 2),
            "场均时长(min)": round(df["时长_min"].mean(), 2),
            "场均击杀(单队)": round((df["场均击杀_v"].mean() + df["场均死亡_v"].mean()) / 2, 2),
            "平均GPM": int(df["GPM_v"].mean()),
            "平均胜率差(pp)": round(df["胜率_v"].max() - df["胜率_v"].min(), 1),
        })
    cmp_df = pd.DataFrame(rows)
    st.markdown("##### 各 Split 核心指标")
    st.dataframe(cmp_df, hide_index=True, width='stretch')

    if len(cmp_df) >= 2:
        left, right = st.columns(2)
        with left:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=cmp_df["赛事"], y=cmp_df["场均时长(min)"],
                                     name="场均时长(min)", mode="lines+markers",
                                     line=dict(color=RED, width=3)))
            fig.add_trace(go.Scatter(x=cmp_df["赛事"], y=cmp_df["场均击杀(单队)"] * 20,
                                     name="场均击杀 ×20", mode="lines+markers",
                                     line=dict(color=BLUE, width=3)))
            st.plotly_chart(style_fig(fig, 380), width='stretch')
        with right:
            fig = px.bar(cmp_df, x="赛事", y="平均GPM", color="赛事",
                         color_discrete_sequence=[GOLD, RED, BLUE], text="平均GPM")
            fig.update_layout(showlegend=False)
            fig.update_traces(textposition="outside", textfont_color="#e8b64c")
            st.plotly_chart(style_fig(fig, 380), width='stretch')


# ============================================================
# 主入口
# ============================================================
st.set_page_config(page_title="LPL 数据分析中心", page_icon="⚔️",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## ⚔️ LPL 数据分析中心")
    st.caption("真实数据 · Games of Legends (gol.gg)")
    page = option_menu(
        None, ["总览", "战队榜", "选手榜", "英雄榜", "赛季对比"],
        icons=["speedometer2", "trophy", "person-badge", "-controller", "graph-up-arrow"],
        default_index=0, styles=MENU_STYLES)
    st.divider()
    tours = list_lpl_tournaments()
    if tours:
        # 默认选最新且有数据的 Split
        splits = [t for t in tours if re.search(r"Split \d$", t)]
        default = max(splits, key=lambda s: int(re.search(r"(\d+)$", s).group(1))) if splits else tours[0]
        tour = st.selectbox("选择赛事", tours,
                            index=tours.index(default) if default in tours else 0)
    else:
        tour = "LPL 2026 Split 3"
        st.error("赛事列表拉取失败, 使用默认赛事 (云端首次部署可能较慢, 刷新重试)")
    st.caption("数据每 30 分钟缓存一次 · 仅供学习演示")

try:
    teams = fetch_teams(tour)
    players = fetch_players(tour)
    champs = fetch_champions(tour)
    if not len(teams) and not len(players):
        st.warning("该赛事暂无统计数据 (可能尚未开赛), 请在侧边栏切换其他赛事。")
        st.stop()
    if page == "总览":
        page_overview(tour, teams, players, champs)
    elif page == "战队榜":
        page_teams(teams)
    elif page == "选手榜":
        page_players(players)
    elif page == "英雄榜":
        page_champions(champs, teams)
    elif page == "赛季对比":
        page_compare(tours, tour)
    st.divider()
    st.caption("数据来源: [Games of Legends](https://gol.gg) · League of Legends 及 LPL 版权归 Riot Games / 腾竞体育所有 · 本页面仅为数据分析 Demo")
except Exception as e:
    st.error(f"数据拉取失败: {type(e).__name__}: {e}")
    st.info("gol.gg 偶尔限流, 请稍后刷新页面; 若在本地运行请检查网络能否访问 gol.gg。")
