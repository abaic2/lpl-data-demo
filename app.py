# -*- coding: utf-8 -*-
"""
LoL 联赛数据分析中心 (LPL/LCK/LCP) · Streamlit Demo
数据来源: Games of Legends (gol.gg) 公开统计页面
"""
import json
import os
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
# 英雄名汉化 (官方 Data Dragon zh_CN 映射, 静态内置)
# ============================================================

def _norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "champion_zh.json"),
          encoding="utf-8") as _f:
    _CHAMP_RAW = json.load(_f)
CHAMP_ZH = {_norm_name(k): v for k, v in _CHAMP_RAW.items()}


def zh_champ(name):
    return CHAMP_ZH.get(_norm_name(name), name)

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


@st.cache_data(ttl=1800, show_spinner="正在从 gol.gg 拉取赛事列表 ...")
def list_all_tournaments():
    """返回 {联赛: [赛事名...]} (按 gol.gg 原序, 新赛事在前), 仅 LPL/LCK/LCP 主联赛"""
    html = _get(BASE + "/players/list/season-ALL/split-ALL/tournament-ALL/")
    m = re.search(r"<select id='cbtournament'.*?</select>", html, re.S)
    if not m:
        return {}
    opts = re.findall(r"<option[^>]*value='([^']+)'[^>]*>\s*([^<]+?)\s*</option>", m.group(0))
    leagues = {lg: [] for lg in ("LPL", "LCK", "LCP")}
    for v, n in opts:
        name = n.strip()
        for lg in leagues:
            # 只收主联赛, 排除 LCK CL 等次级联赛
            if name.startswith(lg + " ") and not name.startswith(lg + " CL"):
                leagues[lg].append(name)
    return leagues


def default_tournament(names):
    """默认赛事启发式: 最新常规赛 (Split N 最大 / Rounds 列表最前), 否则取列表头"""
    splits = [n for n in names if re.search(r"Split \d$", n)]
    if splits:
        return max(splits, key=lambda s: int(re.search(r"(\d+)$", s).group(1)))
    rounds = [n for n in names if "Rounds" in n]
    if rounds:
        return rounds[0]
    return names[0] if names else ""


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
    # 英雄名汉化: 中文名列 (保留英文列用于悬停对照)
    df["英雄中文名"] = df["英雄"].map(zh_champ)
    return df


# ---------- 详情页 (战队/英雄) ----------

def _detail_url(kind, path):
    return urllib.parse.quote(BASE + "/" + kind + "/" + path, safe=":/%")


def _field(html, label):
    """提取 '<td>label:</td><td>value</td>' 的 value, 清洗后返回 str|None"""
    m = re.search(re.escape(label) + r"\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.S)
    if not m:
        return None
    v = _cell_text(m.group(1))
    return v if v not in ("", "-", "&nbsp;") else None


def _num(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", v))
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_team_ids(tournament):
    tok = urllib.parse.quote(tournament)
    html = _get(BASE + "/teams/list/season-ALL/split-ALL/tournament-%s/" % tok)
    ids = {}
    for tid, name in re.findall(
            r"team-stats/(\d+)/[^>]*>\s*([^<>]+?)\s*</a>", html):
        ids.setdefault(name.strip(), tid)
    return ids


@st.cache_data(ttl=1800, show_spinner="正在拉取战队详情 ...")
def fetch_team_detail(tournament, team_id):
    tok = urllib.parse.quote(tournament)
    html = _get(_detail_url("teams", "team-stats/%s/split-ALL/tournament-%s/" % (team_id, tok)))
    d = {
        "gpm": _num(_field(html, "Gold Per Minute:")),
        "gdm": _num(_field(html, "Gold Differential per Minute:")),
        "gd15": _num(_field(html, "Gold Differential at 15 min:")),
        "wr_ahead15": _field(html, "Win Rate when ahead at 15 min:"),
        "csm": _num(_field(html, "CS Per Minute:")),
        "csd15": _num(_field(html, "CS Differential at 15 min:")),
        "td15": _num(_field(html, "Tower Differential at 15 min:")),
        "avg_td": _num(_field(html, "Avg. Tower Difference:")),
        "dpm": _num(_field(html, "Damage Per Minute:")),
        "fb": _field(html, "First Blood:"),
        "plates": _field(html, "Plates / game"),
        "dragons": _field(html, "Dragons / game:"),
        "grubs": _field(html, "Voidgrubs / game:"),
        "herald": _field(html, "Herald / game:"),
        "nashors": _field(html, "Nashors / game:"),
        "vspm": _num(_field(html, "Vision Score Per Minute:")),
        "wpm": _num(_field(html, "Wards Per Minute:")),
        "vwpm": _num(_field(html, "Vision Wards Per Minute:")),
    }
    # 蓝/红方胜负 (图表 JS 数据)
    m = re.search(r"WRData\s*=\s*.*?Wins.*?data\s*:\s*\[([^\]]*)\].*?"
                  r"Losses.*?data\s*:\s*\[([^\]]*)\]", html, re.S)
    if m:
        def _arr(s):
            return [int(x) if x.strip().isdigit() else 0 for x in s.split(",")]
        w, l = _arr(m.group(1)), _arr(m.group(2))
        d["blue_w"], d["blue_l"] = (w + [0, 0])[:2]
        d["red_w"], d["red_l"] = (l + [0, 0])[:2]
    # 选手阵容表 (最后一组含 Champions played 的表)
    d["roster"] = []
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        if "Champions played" not in tb:
            continue
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            if len(cells) < 8:
                continue
            hero_pool = re.findall(
                r"([A-Za-z][A-Za-z' .&-]*?)\s*Winrate\s*:\s*([\d.\-]+)%\s*KDA\s*:\s*([\d.\-]+)\s*(\d+)",
                _cell_text(cells[7]).replace("Winrate : ", "Winrate : "))
            d["roster"].append({
                "位置": _cell_text(cells[0]),
                "选手": _cell_text(cells[1]),
                "KDA": _cell_text(cells[2]),
                "参团率": _cell_text(cells[3]),
                "分均视野分": _cell_text(cells[4]),
                "伤害占比": _cell_text(cells[5]),
                "经济占比": _cell_text(cells[6]),
                "英雄池": hero_pool,
            })
        break
    return d


@st.cache_data(ttl=1800, show_spinner="正在聚合各战队英雄池 ...")
def fetch_team_pools(tournament):
    """聚合全部战队详情 -> {战队: {"roster": [...], "pool": {英雄: (胜率, 场次)}}},
    同时产出英雄->位置映射 (基于本届实际登场) 与战队详情缓存 dict"""
    ids = fetch_team_ids(tournament)
    details, pools, role_map = {}, {}, {}
    for name, tid in ids.items():
        d = fetch_team_detail(tournament, tid)
        details[name] = d
        pool = {}
        for r in d.get("roster", []):
            role = r.get("位置", "")
            for h, wr, _kda, games in r.get("英雄池", []):
                g = int(games) if games.isdigit() else 0
                try:
                    w = float(wr)
                except ValueError:
                    w = None
                if w is None:
                    continue
                old = pool.get(h)
                if not old or g > old[1]:
                    pool[h] = (w, g)
                role_map.setdefault(h, role)
        pools[name] = {"roster": d.get("roster", []), "pool": pool}
    return {"details": details, "pools": pools, "role_map": role_map}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_champion_ids(tournament):
    tok = urllib.parse.quote(tournament)
    html = _get(BASE + "/champion/list/season-ALL/split-ALL/tournament-%s/" % tok)
    ids = {}
    for cid, raw in re.findall(
            r"champion-stats/(\d+)/[^>]*>(.*?)</a>", html, re.S):
        name = _cell_text(raw)
        if name:
            ids.setdefault(name, cid)
    return ids


@st.cache_data(ttl=1800, show_spinner="正在拉取英雄详情 ...")
def fetch_champion_detail(tournament, champ_id):
    tok = urllib.parse.quote(tournament)
    html = _get(_detail_url("champion", "champion-stats/%s/season-ALL/split-ALL/tournament-%s/"
                            % (champ_id, tok)))
    bans = _field(html, "Bans:")
    picks = _field(html, "Picks:")
    d = {
        "bans": bans, "picks": picks,
        "prio": _field(html, "Priority Score:"),
        "series": _field(html, "Presence by Series:"),
        "avg_round": _field(html, "Avg Round Picked:"),
        "wr": _field(html, "Win rate:"),
        "roles": [],
    }
    m_role = re.search(r"<th[^>]*>\s*Role\s*</th>", html)
    if m_role:
        seg = html[m_role.start():]
        end = seg.find("</tbody>")
        tb = seg[:end if end > 0 else 3500]
        # 分路表的胜率列内嵌条形图小表格, 先剥离避免列错位
        tb = re.sub(r"<table class=.tablebarg[^>]*>.*?</table>", " ", tb, flags=re.S)
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            vals = [_cell_text(c) for c in cells]
            vals = [v for v in vals if v]
            if len(vals) >= 5 and vals[0] in ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT"):
                d["roles"].append(vals[:5])
    return d


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
            LoL 联赛数据分析中心
            <span style="font-size:12px;font-weight:400;color:#e8b64c;
              border:1px solid rgba(232,182,76,.4);border-radius:20px;padding:2px 10px;
              margin-left:10px;vertical-align:middle;">LPL · LCK · LCP · 真实数据 gol.gg</span>
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
    hero(tour, "总览 · 本届赛事核心指标与头部榜单")
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
    xlabels = [zh_c + " " + en for zh_c, en in zip(d["英雄中文名"], d["英雄"])]
    fig = go.Figure()
    fig.add_bar(x=xlabels, y=d["选取_v"], name="选取", marker_color=RED,
                customdata=d["英雄"], hovertemplate="%{customdata}<br>选取: %{y}<extra></extra>")
    fig.add_bar(x=xlabels, y=d["禁用_v"], name="禁用", marker_color="#8a5cf6",
                customdata=d["英雄"], hovertemplate="%{customdata}<br>禁用: %{y}<extra></extra>")
    fig.update_layout(barmode="group")
    st.plotly_chart(style_fig(fig, 340), width='stretch')


def _metric_block(cols, items):
    """在若干列里排布 (标签, 值) 指标"""
    per = max(1, len(items) // len(cols) + (1 if len(items) % len(cols) else 0))
    for ci, col in enumerate(cols):
        with col:
            for label, val in items[ci * per:(ci + 1) * per]:
                st.metric(label, val if val not in (None, "", "-") else "暂无")


def render_team_detail(tour, team_name):
    tids = fetch_team_ids(tour)
    tid = tids.get(team_name)
    if not tid:
        st.warning("未找到该战队详情数据。")
        return
    d = fetch_team_detail(tour, tid)
    st.markdown(f"**{team_name} · 深度数据**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("**💰 经济运营**")
        st.metric("分均经济 GPM", d["gpm"])
        st.metric("每分钟经济差", ("+" if (d["gdm"] or 0) > 0 else "") + str(d["gdm"]))
        st.metric("15分钟经济差", d["gd15"])
        st.metric("15分钟领先时胜率", d["wr_ahead15"] or "暂无")
    with c2:
        st.markdown("**⚔️ 进攻输出**")
        st.metric("分均伤害 DPM", d["dpm"])
        st.metric("一血率", d["fb"] or "暂无")
        st.metric("分均补刀 CSM", d["csm"])
        st.metric("15分钟补刀差", d["csd15"])
    with c3:
        st.markdown("**🐉 资源控制**")
        st.metric("场均小龙", d["dragons"] or "暂无")
        st.metric("场均虚空幼虫", d["grubs"] or "暂无")
        st.metric("场均峡谷先锋", d["herald"] or "暂无")
        st.metric("场均男爵", d["nashors"] or "暂无")
    with c4:
        st.markdown("**👁️ 视野与边路**")
        st.metric("分均视野分 VSPM", d["vspm"])
        st.metric("分均排眼", d["vwpm"])
        bw, bl = d.get("blue_w", 0), d.get("blue_l", 0)
        rw, rl = d.get("red_w", 0), d.get("red_l", 0)
        st.metric("蓝方战绩", f"{bw} 胜 {bl} 负")
        st.metric("红方战绩", f"{rw} 胜 {rl} 负")

    # 分路胜负 + 平均塔差
    left, right = st.columns([1, 2])
    with left:
        if bw + bl + rw + rl:
            fig = go.Figure(data=[go.Pie(
                labels=["蓝方胜", "蓝方负", "红方胜", "红方负"],
                values=[bw, bl, rw, rl], hole=0.55,
                marker=dict(colors=[RED, "#3a3f4d", GOLD, "#4a4230"]))])
            fig.update_layout(title_text="分路胜负分布", **{k: v for k, v in PLOTLY_LAYOUT.items() if k != "height"})
            st.plotly_chart(style_fig(fig, 260), width='stretch')
    with right:
        st.markdown("**👥 首发阵容与英雄池**")
        for r in d.get("roster", [])[:7]:
            pool = r.get("英雄池") or []
            pool_txt = " · ".join(
                f"{zh_champ(h)} {wr}%" for h, wr, _, _ in pool[:3]) if pool else ""
            st.markdown(
                f"`{r['位置']}` **{r['选手']}** — KDA {r['KDA']} · 参团 {r['参团率']} · "
                f"伤害占比 {r['伤害占比']} · 经济占比 {r['经济占比']}"
                + (f" <br><small>常备英雄: {pool_txt}</small>" if pool_txt else ""),
                unsafe_allow_html=True)


def page_teams(tour, teams):
    hero("战队页 · 战队榜单 / 风格对比 / 单队深度数据", "战队页 · 数据口径: 当前所选赛事")
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

    st.divider()
    st.markdown("##### 🔍 单队深度数据")
    sel = st.selectbox("选择战队", teams["战队"].tolist())
    render_team_detail(tour, sel)


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


def page_champions(tour, champs):
    hero("英雄页 · 英雄 BP / 强度分析 / 单英雄深度数据", "英雄页 · 选取/禁用/胜率全覆盖")
    n_total = int(champs["选取_v"].sum() + champs["禁用_v"].sum())
    st.markdown(f"##### 英雄数据总表 (共 {len(champs)} 个英雄登场, BP 总人次 {n_total})")
    show = champs[["英雄中文名", "英雄", "选取", "禁用", "BP率", "胜率", "KDA", "DPM", "CSM"]].copy()
    show.columns = ["英雄", "英文名", "选取", "禁用", "BP率", "胜率", "KDA", "DPM", "CSM"]
    st.dataframe(show, hide_index=True, width='stretch', height=440)

    left, right = st.columns(2)
    with left:
        st.markdown("##### 强度四象限: 胜率 vs BP率")
        fig = px.scatter(champs, x="BP率_v", y="胜率_v", text="英雄中文名",
                         size="选取_v", color="胜率_v",
                         color_continuous_scale=["#5c667e", "#4c8de5", "#e5484d"],
                         hover_data={"英雄": True, "选取": True, "禁用": True, "KDA": True})
        fig.add_hline(y=50, line_dash="dot", line_color="#39435c")
        fig.update_traces(textposition="top center", textfont_size=8)
        st.plotly_chart(style_fig(fig, 430), width='stretch')
    with right:
        st.markdown("##### 禁用榜 TOP 12")
        d = champs.sort_values("禁用_v", ascending=False).head(12)
        fig = px.bar(d, x="禁用_v", y="英雄中文名", orientation="h", color="禁用_v",
                     color_continuous_scale=["#1f1533", "#8a5cf6"], text="禁用",
                     custom_data=["英雄"])
        fig.update_traces(hovertemplate="%{customdata[0]} (%{y})<br>禁用: %{x}<extra></extra>")
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition="outside", textfont_color="#c3a9f5")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 430), width='stretch')

    st.divider()
    st.markdown("##### 🔍 单英雄深度数据")
    sel = st.selectbox("选择英雄", champs["英雄中文名"].tolist(),
                       format_func=lambda n: n)
    row = champs[champs["英雄中文名"] == sel].iloc[0]
    cd = fetch_champion_detail(tour, fetch_champion_ids(tour).get(row["英雄"], ""))
    st.markdown(f"**{sel} ({row['英雄']}) · BP 明细**")
    m = re.match(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", cd.get("bans") or "")
    pm = re.match(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", cd.get("picks") or "")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("总禁用", m.group(1) if m else cd.get("bans") or "0",
              ("红 %s / 蓝 %s" % (m.group(2), m.group(3))) if m else None)
    c2.metric("总选取", pm.group(1) if pm else cd.get("picks") or "0",
              ("红 %s / 蓝 %s" % (pm.group(2), pm.group(3))) if pm else None)
    c3.metric("优先级评分", cd.get("prio") or "-")
    c4.metric("系列赛存在率", cd.get("series") or "-")
    c5.metric("平均选取轮次", cd.get("avg_round") or "-")
    c6.metric("当前战绩", cd.get("wr") or "-")
    if cd.get("roles"):
        st.markdown("**分路表现**")
        rdf = pd.DataFrame(cd["roles"], columns=["分路", "场次", "胜率", "KDA", "分均伤害"])
        st.dataframe(rdf, hide_index=True, width='stretch')
    else:
        st.caption("该英雄暂无分路明细数据。")


# ============================================================
# 胜率 / 比分预测
# ============================================================

def _side_wr(d, side):
    w, l = d.get(side + "_w") or 0, d.get(side + "_l") or 0
    return w / (w + l) if (w + l) else None


def _series_probs(per_game, need):
    """逐场胜率 -> 系列赛比分概率分布, key=(蓝方胜场, 红方胜场)"""
    dist = {}

    def rec(i, a, b, p):
        if a == need or b == need:
            dist[(a, b)] = dist.get((a, b), 0.0) + p
            return
        if i >= len(per_game):
            return
        rec(i + 1, a + 1, b, p * per_game[i])
        rec(i + 1, a, b + 1, p * (1 - per_game[i]))

    rec(0, 0, 0, 1.0)
    return dist


def _power_scores(teams):
    """差异化实力评分: 多维真实指标 z-score 加权, 每队得分不同"""
    def z(s):
        sd = s.std()
        return (s - s.mean()) / sd if sd else s * 0
    diff = teams["场均击杀_v"] - teams["场均死亡_v"]
    return (0.35 * z(teams["胜率_v"]) + 0.20 * z(diff)
            + 0.20 * z(teams["场均推塔_v"]) + 0.15 * z(teams["GPM_v"])
            + 0.10 * z(-teams["时长_min"]))


def _logistic(x):
    return 1 / (1 + pow(2.718281828, -x))


def page_predict(tour, teams):
    hero("胜率预测 · 差异化实力评分 + 分边修正 + 比分概率", "预测页 · 多维指标评分模型 (娱乐向)")
    teams = teams.copy()
    teams["实力评分"] = _power_scores(teams)
    ranked = teams.sort_values("实力评分", ascending=False).reset_index(drop=True)
    names = ranked["战队"].tolist()
    c0, c1 = st.columns(2)
    team_a = c0.selectbox("🔵 蓝方队伍", names, index=0)
    team_b = c1.selectbox("🔴 红方队伍", names, index=1 if len(names) > 1 else 0)
    if team_a == team_b:
        st.warning("请选择两支不同的队伍。")
        return

    ra_row = ranked[ranked["战队"] == team_a].iloc[0]
    rb_row = ranked[ranked["战队"] == team_b].iloc[0]
    pow_a, pow_b = ra_row["实力评分"], rb_row["实力评分"]

    st.markdown("##### 差异化实力评分 (每队独立, 联赛内标准化)")
    k0, k1, k2 = st.columns(3)
    k0.metric(f"{team_a} 综合评分", f"{pow_a:+.2f}",
              f"联赛第 {int(ra_row.name) + 1} 名")
    k1.metric(f"{team_b} 综合评分", f"{pow_b:+.2f}",
              f"联赛第 {int(rb_row.name) + 1} 名")
    k2.metric("评分差", f"{pow_a - pow_b:+.2f}")

    # 评分构成对比 (z 分量)
    def _components(row):
        def z(col, invert=False):
            s = teams[col]
            v = row[col] * (-1 if invert else 1)
            sd = s.std()
            return ((s * (-1 if invert else 1) - (s * (-1 if invert else 1)).mean()) / sd) if sd else 0
        return {
            "胜率": z("胜率_v"),
            "击杀差": z("场均击杀_v") - z("场均死亡_v"),
            "推塔": z("场均推塔_v"),
            "经济 GPM": z("GPM_v"),
            "节奏(时长反向)": z("时长_min", invert=True),
        }

    comp_a, comp_b = _components(ra_row), _components(rb_row)
    labels = list(comp_a.keys())
    fig = go.Figure()
    fig.add_bar(y=labels, x=[comp_a[k] for k in labels], name=team_a,
                orientation="h", marker_color=BLUE)
    fig.add_bar(y=labels, x=[comp_b[k] for k in labels], name=team_b,
                orientation="h", marker_color=RED)
    fig.update_layout(barmode="group", xaxis_title="联赛内 z-score")
    st.plotly_chart(style_fig(fig, 320), width='stretch')

    # 分边修正
    tids = fetch_team_ids(tour)
    da = fetch_team_detail(tour, tids.get(team_a, ""))
    db = fetch_team_detail(tour, tids.get(team_b, ""))
    wa, ra_w = _side_wr(da, "blue"), _side_wr(da, "red")
    wb, rb_w = _side_wr(db, "blue"), _side_wr(db, "red")
    p_a_blue_side = 0.5 * (wa if wa is not None else 0.5) + 0.5 * (1 - (rb_w if rb_w is not None else 0.5))
    p_a_red_side = 0.5 * (1 - (wb if wb is not None else 0.5)) + 0.5 * (ra_w if ra_w is not None else 0.5)

    st.markdown("##### 模型输入 (两队真实分边战绩)")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric(f"{team_a} 蓝/红方胜率",
               (f"{wa*100:.0f}%" if wa is not None else "-") + " / " +
               (f"{ra_w*100:.0f}%" if ra_w is not None else "-"))
    mc2.metric(f"{team_b} 蓝/红方胜率",
               (f"{wb*100:.0f}%" if wb is not None else "-") + " / " +
               (f"{rb_w*100:.0f}%" if rb_w is not None else "-"))
    mc3.metric("场地顺序", "A 队先蓝, 交替")

    # 逐场胜率 = 实力分模型与分边模型各占一半
    p_power = _logistic(1.8 * (pow_a - pow_b))
    p_game_blue = 0.5 * p_power + 0.5 * p_a_blue_side
    # A 在红方局: P(B 蓝) = 0.5*实力分(B) + 0.5*(1 - p_a_red_side)
    p_game_red = 1 - (0.5 * _logistic(1.8 * (pow_b - pow_a)) + 0.5 * (1 - p_a_red_side))

    st.markdown("##### 逐场与系列赛预测")
    bo3 = [p_game_blue, p_game_red, p_game_blue]
    bo5 = [p_game_blue, p_game_red, p_game_blue, p_game_red, p_game_blue]
    d3, d5 = _series_probs(bo3, 2), _series_probs(bo5, 3)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("实力分模型 BO1", f"{p_power*100:.0f}%")
    k2.metric("分边模型 BO1 (A 先蓝)", f"{p_a_blue_side*100:.0f}%")
    k3.metric("综合 BO1 (蓝方第 1 局)", f"{p_game_blue*100:.0f}%")
    k4.metric("BO3 系列赛胜率 (蓝方)",
              f"{sum(p for (a, b), p in d3.items() if a > b)*100:.0f}%")

    left, right = st.columns(2)
    with left:
        st.markdown("**BO3 比分概率**")
        rows3 = [{"比分": f"{a} : {b}", "概率": f"{p*100:.1f}%",
                  "_p": p} for (a, b), p in sorted(d3.items(), key=lambda kv: -kv[1])]
        fig = px.bar(pd.DataFrame(rows3), x="_p", y="比分", orientation="h",
                     color="_p", color_continuous_scale=["#3a1a20", "#e5484d"],
                     text="概率", labels={"_p": "概率"})
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 240), width='stretch')
    with right:
        st.markdown("**BO5 比分概率**")
        rows5 = [{"比分": f"{a} : {b}", "概率": f"{p*100:.1f}%",
                  "_p": p} for (a, b), p in sorted(d5.items(), key=lambda kv: -kv[1])]
        fig = px.bar(pd.DataFrame(rows5), x="_p", y="比分", orientation="h",
                     color="_p", color_continuous_scale=["#241a08", "#e8b64c"],
                     text="概率", labels={"_p": "概率"})
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style_fig(fig, 240), width='stretch')

    st.markdown("##### 关键指标对比 (本届数据)")
    cmp_items = [
        ("15分钟经济差", (da.get("gd15") or 0), (db.get("gd15") or 0)),
        ("分均伤害 DPM", (da.get("dpm") or 0), (db.get("dpm") or 0)),
        ("分均经济 GPM", (da.get("gpm") or 0), (db.get("gpm") or 0)),
        ("场均小龙", float(re.match(r"[\d.]+", da.get("dragons") or "0").group() or 0),
         float(re.match(r"[\d.]+", db.get("dragons") or "0").group() or 0)),
        ("场均男爵", float(re.match(r"[\d.]+", da.get("nashors") or "0").group() or 0),
         float(re.match(r"[\d.]+", db.get("nashors") or "0").group() or 0)),
        ("分均视野分", (da.get("vspm") or 0), (db.get("vspm") or 0)),
    ]
    fig = go.Figure()
    fig.add_bar(y=[x[0] for x in cmp_items], x=[x[1] for x in cmp_items],
                name=team_a, orientation="h", marker_color=BLUE)
    fig.add_bar(y=[x[0] for x in cmp_items], x=[x[2] for x in cmp_items],
                name=team_b, orientation="h", marker_color=RED)
    fig.update_layout(barmode="group")
    st.plotly_chart(style_fig(fig, 340), width='stretch')
    st.caption("模型说明: 实力评分 = 0.35×胜率 + 0.20×击杀差 + 0.20×推塔 + 0.15×GPM + "
               "0.10×节奏 (联赛内 z-score, 每队得分不同); 逐场胜率 = 实力分模型与分边战绩模型各占 50%, "
               "场地按 A 队先蓝交替。仅供学习演示, 不构成任何投注建议。")


# ============================================================
# BP 模拟
# ============================================================

def _champ_zscores(champs):
    def z(col):
        s = champs[col]
        sd = s.std()
        return (s - s.mean()) / sd if sd else s * 0
    return 0.5 * z("胜率_v") + 0.3 * z("DPM_v") + 0.2 * z("KDA_v")


ROLE_ZH = {"TOP": "上单", "JUNGLE": "打野", "MID": "中单", "BOT": "ADC", "SUPPORT": "辅助"}


def _pool_metrics(team, tp):
    """返回该队英雄池 {英文英雄名: (本队胜率, 场次)} 与选手列表"""
    info = tp["pools"].get(team, {})
    return info.get("pool", {}), info.get("roster", [])


def _pick_score(en, team_pool, score_map):
    """评分 = 全局 z-score + 本队熟练度加成 (池内英雄按本队真实胜率)"""
    s = score_map.get(en, 0.0)
    p = team_pool.get(en)
    if p:
        s += (p[0] - 50) / 10 * 0.5
    return s


def page_bp(tour, champs):
    hero("BP 模拟 · 战队对抗 / 位置分栏 / 英雄池推荐", "BP 页 · 基于两队本届真实英雄池的模拟 (娱乐向)")
    tp = fetch_team_pools(tour)
    team_names = sorted(tp["pools"].keys())
    if not team_names:
        st.warning("战队英雄池数据拉取失败, 请稍后刷新。")
        return

    c0, c1 = st.columns(2)
    blue_team = c0.selectbox("🔵 蓝方战队", team_names, index=0)
    red_team = c1.selectbox("🔴 红方战队", team_names,
                            index=1 if len(team_names) > 1 else 0)
    if blue_team == red_team:
        st.warning("请选择两支不同的战队。")
        return
    blue_pool, blue_roster = _pool_metrics(blue_team, tp)
    red_pool, red_roster = _pool_metrics(red_team, tp)

    if "bp_bans" not in st.session_state:
        st.session_state.bp_bans = []
        st.session_state.bp_blue = []
        st.session_state.bp_red = []
        st.session_state.bp_history = []
    bans, blue, red = (st.session_state.bp_bans, st.session_state.bp_blue,
                       st.session_state.bp_red)

    used = bans + blue + red
    pool = champs[~champs["英雄"].isin(used)].copy()
    score_map = dict(zip(champs["英雄"], _champ_zscores(champs)))

    # 位置标注 (基于本届各队实际登场的英雄->位置映射)
    pool["位置"] = pool["英雄"].map(lambda h: ROLE_ZH.get(tp["role_map"].get(h, ""), "其他"))

    st.markdown(f"**当前进度** — 禁用 {len(bans)} · 蓝方 {len(blue)} · 红方 {len(red)}"
                f" · 剩余英雄池 {len(pool)}")
    left, mid, right = st.columns([2, 3, 2])

    def _roster_block(team, picks, team_pool):
        st.markdown(f"#### {'🔵' if team == blue_team else '🔴'} {team}")
        if picks:
            rows = []
            for en in picks:
                p = team_pool.get(en)
                rows.append({
                    "英雄": zh_champ(en), "英文名": en,
                    "本队胜率": f"{p[0]:.0f}% ({p[1]}场)" if p else "场外选人",
                    "评分": f"{_pick_score(en, team_pool, score_map):+.2f}",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
            st.metric("阵容综合评分", f"{sum(_pick_score(x, team_pool, score_map) for x in picks):+.2f}",
                      f"本队英雄池 {sum(1 for x in picks if x in team_pool)}/{len(picks)}")
        else:
            st.caption("尚未选取")
        pool_txt = []
        for r in (blue_roster if team == blue_team else red_roster):
            tops = sorted(r.get("英雄池") or [], key=lambda x: -(float(x[1]) if x[1] else 0))[:2]
            if tops:
                pool_txt.append(f"`{ROLE_ZH.get(r['位置'], r['位置'])}` {r['选手']}: "
                                + " / ".join(f"{zh_champ(h)} {wr}%" for h, wr, _k, _g in tops))
        if pool_txt:
            with st.expander("👥 本队选手英雄池 (前 2)"):
                st.markdown("<br>".join(pool_txt), unsafe_allow_html=True)

    with left:
        _roster_block(blue_team, blue, blue_pool)
    with right:
        _roster_block(red_team, red, red_pool)

    with mid:
        st.markdown("#### 🎯 操作台")
        if len(pool) == 0:
            st.info("英雄池已用完! 点下方重置开始新一局。")
        else:
            # 搜索 + 位置筛选
            q = st.text_input("🔍 搜索英雄 (中文名或英文名)", "").strip().lower()
            role = st.radio("位置", ["全部", "上单", "打野", "中单", "ADC", "辅助", "其他"],
                            horizontal=True)
            fp = pool
            if role != "全部":
                fp = fp[fp["位置"] == role]
            if q:
                fp = fp[fp["英雄"].str.lower().str.contains(q, regex=False)
                        | fp["英雄中文名"].str.contains(q, regex=False)]
            if len(fp) == 0:
                st.info("没有符合条件的英雄。")
            else:
                fp = fp.sort_values("BP率_v", ascending=False)
                options = (fp["英雄中文名"] + " (" + fp["英雄"] + ") · 胜率 " + fp["胜率"]
                           + " · BP率 " + fp["BP率"]).tolist()
                en_of = dict(zip(options, fp["英雄"]))
                sel = st.selectbox(f"选择英雄 ({len(fp)} 个)", options)
                sel_en = en_of[sel]
                b1, b2, b3 = st.columns(3)
                if b1.button("🚫 禁用", use_container_width=True):
                    st.session_state.bp_history.append(("ban", sel_en))
                    bans.append(sel_en)
                if b2.button("🔵 蓝方拿", use_container_width=True):
                    st.session_state.bp_history.append(("blue", sel_en))
                    blue.append(sel_en)
                if b3.button("🔴 红方拿", use_container_width=True):
                    st.session_state.bp_history.append(("red", sel_en))
                    red.append(sel_en)
        b4, b5 = st.columns(2)
        if b4.button("↩️ 撤销", use_container_width=True):
            if st.session_state.bp_history:
                act, name = st.session_state.bp_history.pop()
                {"ban": bans, "blue": blue, "red": red}[act].remove(name)
        if b5.button("🗑️ 重置", use_container_width=True):
            st.session_state.bp_bans = []
            st.session_state.bp_blue = []
            st.session_state.bp_red = []
            st.session_state.bp_history = []

        # 基于本队英雄池的推荐
        st.markdown("**💡 英雄池推荐 (基于两队本届真实选用)**")

        def _rec(team, opp_pool, kind):
            my = tp["pools"].get(team, {}).get("pool", {})
            cand = [(h, w, g) for h, (w, g) in my.items()
                    if h not in used and w is not None]
            if kind == "ban":
                # 建议禁用: 对方池中最强且仍可选的
                opp = [(h, w, g) for h, (w, g) in opp_pool.items()
                       if h not in used and w is not None]
                cand = sorted(opp, key=lambda x: (-x[1], -x[2]))[:3]
                tag = "对方绝活"
            else:
                cand = sorted(cand, key=lambda x: (-x[1], -x[2]))[:3]
                tag = "本队绝活"
            if not cand:
                return tag, None
            h, w, g = cand[0]
            zh = zh_champ(h)
            extra = f" · 本队 {w:.0f}% ({g}场)" if kind != "ban" else \
                f" · 对方 {w:.0f}% ({g}场)"
            return tag, f"**{zh}** ({h}){extra}"

        if len(pool):
            t1, r1 = _rec(blue_team, red_pool, "pick")
            t2, r2 = _rec(red_team, blue_pool, "pick")
            t3, r3 = _rec(blue_team, red_pool, "ban")
            t4, r4 = _rec(red_team, blue_pool, "ban")
            st.markdown(f"- 🔵 蓝方建议选取 ({t1}): {r1 or '池内已无'}")
            st.markdown(f"- 🔴 红方建议选取 ({t2}): {r2 or '池内已无'}")
            st.markdown(f"- 🚫 蓝方建议禁用 ({t3}): {r3 or '无'}")
            st.markdown(f"- 🚫 红方建议禁用 ({t4}): {r4 or '无'}")
            bp = pool.sort_values("优先级_v", ascending=False).head(1)
            if len(bp):
                st.markdown(f"- 📈 全局版本优先级最高: **{bp.iloc[0]['英雄中文名']}** "
                            f"(优先级 {bp.iloc[0]['优先级']})")
        if bans:
            st.markdown("**已禁用**: " + "、".join(zh_champ(x) for x in bans))

    st.caption("规则简化说明: 未还原官方 BP 轮换顺序; 评分 = 全局 z-score (0.5 胜率 + 0.3 DPM + "
               "0.2 KDA) + 本队熟练度加成 (英雄在本队真实胜率, 池外选人无加成); "
               "推荐基于两队本届实际选用的英雄池, 仅供娱乐参考。")


def page_compare(tours, tour):
    lg = tour.split(" ")[0] if tour else "LPL"
    year = (re.search(r"(20\d\d)", tour).group(1) if re.search(r"(20\d\d)", tour) else "")
    hero("赛季对比页 · 同年各赛事横向对比", "赛季对比页 · 拉取该联赛多届数据自动对比")
    # 排除次级/表演性质阶段, 按年份过滤; gol.gg 列表新赛事在前
    stages = [t for t in tours if t.startswith(lg + " ") and " CL " not in t
              and (not year or year in t)] or list(tours)
    frames = {}
    with st.status("正在拉取各赛事战队数据 ...", expanded=True) as s:
        for t in stages:
            st.write("→ " + t)
            frames[t] = fetch_teams(t)
        s.update(label="拉取完成", state="complete")
    rows = []
    for t, df in frames.items():
        if not len(df):
            continue
        rows.append({
            "赛事": t.replace(lg + " " + year + " ", "") if year else t,
            "战队数": len(df),
            "总场次": int(df["场次_v"].sum() // 2),
            "场均时长(min)": round(df["时长_min"].mean(), 2),
            "场均击杀(单队)": round((df["场均击杀_v"].mean() + df["场均死亡_v"].mean()) / 2, 2),
            "平均GPM": int(df["GPM_v"].mean()),
            "平均胜率差(pp)": round(df["胜率_v"].max() - df["胜率_v"].min(), 1),
        })
    cmp_df = pd.DataFrame(rows)
    st.markdown(f"##### {lg} 各赛事核心指标")
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
st.set_page_config(page_title="LoL 联赛数据分析中心", page_icon="⚔️",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## ⚔️ 联赛数据分析中心")
    st.caption("LPL · LCK · LCP · 真实数据 gol.gg")
    page = option_menu(
        None, ["总览", "战队榜", "选手榜", "英雄榜", "胜率预测", "BP 模拟", "赛季对比"],
        icons=["speedometer2", "trophy", "person-badge", "controller",
               "lightning-charge", "shuffle", "graph-up-arrow"],
        default_index=0, styles=MENU_STYLES)
    st.divider()
    leagues = list_all_tournaments()
    league = st.selectbox("选择联赛", ["LPL", "LCK", "LCP"])
    tours = leagues.get(league, [])
    if tours:
        tour = st.selectbox("选择赛事", tours,
                            index=tours.index(default_tournament(tours))
                            if default_tournament(tours) in tours else 0)
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
        page_teams(tour, teams)
    elif page == "选手榜":
        page_players(players)
    elif page == "英雄榜":
        page_champions(tour, champs)
    elif page == "胜率预测":
        page_predict(tour, teams)
    elif page == "BP 模拟":
        page_bp(tour, champs)
    elif page == "赛季对比":
        page_compare(tours, tour)
    st.divider()
    st.caption("数据来源: [Games of Legends](https://gol.gg) · League of Legends 及 LPL/LCK/LCP 版权归 Riot Games 及各赛区版权方所有 · 本页面仅为数据分析 Demo")
except Exception as e:
    st.error(f"数据拉取失败: {type(e).__name__}: {e}")
    st.info("gol.gg 偶尔限流, 请稍后刷新页面; 若在本地运行请检查网络能否访问 gol.gg。")
