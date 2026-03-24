import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 系统核心逻辑引擎 ---
class DwellTimeEngine:
    def __init__(self, alpha=0.3):
        self.alpha = alpha
        
    def calculate_step(self, df, new_in, new_out, timestamp):
        # 计算当前在场人数 (L)
        prev_occ = df.iloc[-1]['occupancy'] if not df.empty else 0
        current_occ = max(0, prev_occ + (new_in - new_out))
        
        # 计算 EMA (平滑进入率 和 平滑在场人数)
        if df.empty:
            ema_in = new_in
            ema_occ = current_occ
        else:
            prev_ema_in = df.iloc[-1]['ema_in']
            prev_ema_occ = df.iloc[-1]['ema_occ']
            ema_in = self.alpha * new_in + (1 - self.alpha) * prev_ema_in
            ema_occ = self.alpha * current_occ + (1 - self.alpha) * prev_ema_occ
        
        # 利特尔法则核心计算: W = L_avg / lambda_avg
        # lambda_avg 需要转换为 "人/分钟"，所以 ema_in / 5
        avg_in_rate = ema_in / 5.0
        dwell_time = ema_occ / avg_in_rate if avg_in_rate > 0 else 0
        
        return {
            'timestamp': timestamp,
            'in_count': new_in,
            'out_count': new_out,
            'occupancy': current_occ,
            'ema_in': ema_in,
            'ema_occ': ema_occ,
            'dwell_time': round(dwell_time, 2)
        }

# --- 2. Streamlit 页面配置 ---
st.set_page_config(page_title="商业广场实时客流监控系统", layout="wide")
st.title("🏙️ 商业广场非侵入式停留时间估算系统")
st.markdown("基于 **Little's Law** 与 **EMA 平滑算法** 的实时监测看板")

# 初始化 Session State (存储数据)
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(columns=[
        'timestamp', 'in_count', 'out_count', 'occupancy', 'ema_in', 'ema_occ', 'dwell_time'
    ])
if 'start_time' not in st.session_state:
    st.session_state.start_time = datetime.now().replace(hour=10, minute=0, second=0)

# --- 3. 侧边栏：数据录入 ---
st.sidebar.header("📥 实时数据录入")
day_type = st.sidebar.selectbox("日期类型", ["工作日", "周末", "节假日/促销日"])
alpha_map = {"工作日": 0.3, "周末": 0.4, "节假日/促销日": 0.6}
engine = DwellTimeEngine(alpha=alpha_map[day_type])

with st.sidebar.form("data_input"):
    in_val = st.number_input("过去 5 分钟进入人数", min_value=0, step=1)
    out_val = st.number_input("过去 5 分钟离开人数", min_value=0, step=1)
    submit = st.form_submit_button("提交数据 (Next 5 Min)")

if submit:
    # 模拟时间推进
    next_time = st.session_state.start_time + timedelta(minutes=5 * len(st.session_state.data))
    new_record = engine.calculate_step(st.session_state.data, in_val, out_val, next_time)
    st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame([new_record])], ignore_index=True)

if st.sidebar.button("🧹 清空数据/重置"):
    st.session_state.data = pd.DataFrame(columns=['timestamp', 'in_count', 'out_count', 'occupancy', 'ema_in', 'ema_occ', 'dwell_time'])
    st.rerun()

# --- 4. 顶部核心指标展示 ---
if not st.session_state.data.empty:
    last_row = st.session_state.data.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("当前在场人数 (L)", f"{int(last_row['occupancy'])} 人")
    col2.metric("平均停留时间 (W)", f"{last_row['dwell_time']} 分钟")
    col3.metric("EMA进入率", f"{round(last_row['ema_in']/5, 2)} 人/min")
    
    total_in = st.session_state.data['in_count'].sum()
    total_out = st.session_state.data['out_count'].sum()
    drift = total_in - total_out
    col4.metric("系统累积误差 (Drift)", f"{int(drift)} 人", delta_color="inverse")

# --- 5. 可视化图表 ---
if not st.session_state.data.empty:
    df = st.session_state.data
    
    # 图表 1: 进出流量对比
    fig_flow = go.Figure()
    fig_flow.add_trace(go.Bar(x=df['timestamp'], y=df['in_count'], name='进入人数', marker_color='#ef553b'))
    fig_flow.add_trace(go.Bar(x=df['timestamp'], y=-df['out_count'], name='离开人数', marker_color='#636efa'))
    fig_flow.update_layout(title="5分钟进出流量 (Traffic Flow)", barmode='relative', height=300)
    st.plotly_chart(fig_flow, use_container_width=True)
    
    # 图表 2: 在场人数与停留时间
    col_left, col_right = st.columns(2)
    
    with col_left:
        fig_occ = go.Figure()
        fig_occ.add_trace(go.Scatter(x=df['timestamp'], y=df['occupancy'], fill='tozeroy', name='实时人数', line_color='#00cc96'))
        fig_occ.update_layout(title="在场人数趋势 (Occupancy)", height=350)
        st.plotly_chart(fig_occ, use_container_width=True)
        
    with col_right:
        fig_dwell = go.Figure()
        # 修复后的代码：使用 .replace(0, None) 或判断，防止除以 0
        raw_in_rate = df['in_count'] / 5.0
        # 如果 rate 为 0，则设为 NaN (Not a Number)，Plotly 会自动忽略这些点而不报错
        raw_w = df['occupancy'] / raw_in_rate.replace(0, float('nan'))
        fig_dwell.add_trace(go.Scatter(x=df['timestamp'], y=raw_w, name='瞬时计算值', mode='markers', marker=dict(size=5, color='gray')))
        # EMA 平滑值
        fig_dwell.add_trace(go.Scatter(x=df['timestamp'], y=df['dwell_time'], name='EMA平滑趋势', line=dict(width=4, color='#ab63fa')))
        fig_dwell.update_layout(title="平均停留时间趋势 (Dwell Time - Minutes)", height=350)
        st.plotly_chart(fig_dwell, use_container_width=True)

# --- 6. 闭店结算模块 ---
# st.divider()
# if st.button("🏁 闭店执行结算与误差校准"):
#     if not st.session_state.data.empty:
#         st.subheader("📊 闭店分析报告")
#         total_in = st.session_state.data['in_count'].sum()
#         total_out = st.session_state.data['out_count'].sum()
#         final_drift = total_in - total_out
        
#         c1, c2 = st.columns(2)
#         c1.write(f"**全天总进入:** {total_in} 人")
#         c1.write(f"**全天总离开:** {total_out} 人")
#         c1.write(f"**未清零误差:** {final_drift} 人")
        
#         if final_drift != 0:
#             st.warning(f"检测到 {final_drift} 人未正常离场。已根据流量权重启动全天分布修正逻辑...")
#             # 简单展示修正逻辑：误差占比
#             drift_rate = (final_drift / total_in) * 100
#             st.info(f"系统整体感应精度: {100 - abs(round(drift_rate, 2))}%")
        
#         st.success("数据已封存。可基于此数据进行 '剩余寿命理论' 的非参数化分布推导。")
#     else:
#         st.error("暂无数据进行结算。")
# --- 6. 闭店结算模块 (修改版) ---
st.divider()
if st.button("🏁 闭店执行结算与误差校准"):
    if not st.session_state.data.empty:
        st.subheader("📊 闭店分析报告")
        
        # 获取最终的数据表
        final_df = st.session_state.data.copy()
        
        # 1. 保存到本地硬盘 (真正的封存)
        file_name = f"mall_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        final_df.to_csv(file_name, index=False)
        st.success(f"✅ 数据已物理封存至文件: {file_name}")

        # 2. 提供网页下载按钮 (方便你保存到别处)
        csv_buffer = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 点击下载封存的 CSV 数据",
            data=csv_buffer,
            file_name=file_name,
            mime='text/csv',
        )

        # 3. 误差展示逻辑 (保持不变)
        total_in = final_df['in_count'].sum()
        total_out = final_df['out_count'].sum()
        final_drift = total_in - total_out
        
        st.write(f"**全天总进入:** {total_in} 人 | **全天总离开:** {total_out} 人")
        st.info(f"**系统累积误差:** {final_drift} 人")
        
    else:
        st.error("暂无数据进行结算。")