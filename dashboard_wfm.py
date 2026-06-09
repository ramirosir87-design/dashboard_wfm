import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import datetime

st.set_page_config(page_title="WFM - Control Clínico de Desvíos", layout="wide", initial_sidebar_state="expanded")

# Custom styled header and glassmorphism styling
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;800&display=swap');
    .main-title { 
        font-family: 'Outfit', sans-serif; 
        font-size:36px !important; 
        font-weight: 800; 
        background: linear-gradient(90deg, #1E3A8A 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 5px; 
    }
    .subtitle { 
        font-family: 'Inter', sans-serif;
        font-size:16px !important; 
        color: #6B7280; 
        margin-bottom: 25px; 
    }
    .section-title {
        font-family: 'Outfit', sans-serif;
        font-size: 22px !important;
        font-weight: 700;
        color: #1E3A8A;
        margin-top: 20px;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">🎯 WFM: Dashboard Clínico de Adherencia y Desvíos</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Auditoría de desvíos y control clínico (Directores a Supervisores)</p>', unsafe_allow_html=True)

# Helper function to convert time/string values to minutes
def convertir_a_minutos(val):
    try:
        if pd.isna(val) or val == '' or val == '-':
            return 0.0
        # If excel parses it as datetime.time
        if hasattr(val, 'hour'):
            return (val.hour * 60) + val.minute + (val.second / 60)
        # If it's a timedelta
        if hasattr(val, 'seconds'):
            return val.seconds / 60.0
            
        val_str = str(val).strip()
        if ':' in val_str:
            partes = val_str.split(':')
            return (int(partes[0]) * 60) + int(partes[1]) + (float(partes[2]) / 60)
        return float(val_str)
    except:
        return 0.0

# Helper to render premium cards
def render_kpi_card(title, value, is_deviated=False, subtitle=""):
    color = '#EF4444' if is_deviated else '#10B981'
    border_color = "rgba(239, 68, 68, 0.3)" if is_deviated else "rgba(16, 185, 129, 0.3)"
    bg_color = "rgba(254, 242, 242, 0.6)" if is_deviated else "rgba(240, 253, 250, 0.6)"
    
    card_html = f"""
    <div style="
        background: {bg_color};
        backdrop-filter: blur(10px);
        border-radius: 12px;
        border: 1px solid {border_color};
        padding: 12px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 10px;
        height: 110px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    ">
        <p style="margin: 0; font-size: 10px; color: #4B5563; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">{title}</p>
        <p style="margin: 4px 0 0 0; font-size: 22px; font-weight: 800; color: {color};">{value}</p>
        <p style="margin: 2px 0 0 0; font-size: 10px; color: #6B7280; font-weight: 500;">{subtitle}</p>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# Helper to check deviations for CH, CAPA, Dev EC, Agen Novedades
def procesar_desvio_generico(df, name, check_schedule_shift=False):
    if df.empty:
        df['Es_Desviado'] = False
        df['Causa_Desvio'] = "Sin datos"
        return df
        
    if 'PROGRAMADO' not in df.columns or 'ACUMULADO' not in df.columns:
        df['Es_Desviado'] = False
        df['Causa_Desvio'] = "Faltan columnas de planificación"
        return df
    
    es_desviado_list = []
    causa_list = []
    
    for idx, row in df.iterrows():
        prog_str = str(row['PROGRAMADO']).strip()
        acum_str = str(row['ACUMULADO']).strip()
        
        is_prog = (prog_str != '00:00:00' and prog_str != '-' and prog_str != '' and prog_str != 'nan')
        is_acum = (acum_str != '00:00:00' and acum_str != '-' and acum_str != '' and acum_str != 'nan')
        
        if is_prog and not is_acum:
            es_desviado_list.append(True)
            causa_list.append(f"Programado ({prog_str}) no realizado")
        elif not is_prog and is_acum:
            acum_min = convertir_a_minutos(row['ACUMULADO'])
            es_desviado_list.append(True)
            causa_list.append(f"Realizado sin programar ({acum_min:.1f} min)")
        elif is_prog and is_acum:
            if check_schedule_shift:
                # Verificar si en el intervalo programado hubo actividad
                val_intervalo = str(row.get(prog_str, '00:00:00')).strip()
                if val_intervalo == '00:00:00' or val_intervalo == '-' or val_intervalo == '0' or val_intervalo == 'nan':
                    es_desviado_list.append(True)
                    causa_list.append(f"Desfase horario (agendado {prog_str}, tomado en otro horario)")
                else:
                    es_desviado_list.append(False)
                    causa_list.append("OK")
            else:
                es_desviado_list.append(False)
                causa_list.append("OK")
        else:
            es_desviado_list.append(False)
            causa_list.append("OK")
            
    df['Es_Desviado'] = es_desviado_list
    df['Causa_Desvio'] = causa_list
    return df

# Count number of intervals an agent spent in a certain state
def contar_frecuencia_intervalos(row, columns):
    freq = 0
    for col in columns:
        val = row[col]
        if pd.notna(val) and str(val) != '00:00:00' and val != 0 and str(val) != '0' and str(val) != 'nan' and str(val) != '':
            freq += 1
    return freq

# Parse start time and shift duration into a set of 30-minute intervals
def obtener_rango_horas(start_time_str, duration_hours):
    try:
        start_time_str = start_time_str.strip()
        if start_time_str in ['', '-', 'nan']:
            return set()
            
        parts = start_time_str.split(':')
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        
        start_dt = datetime.datetime(2026, 6, 8, h, m)
        duration_min = int(float(duration_hours) * 60)
        
        intervals = []
        current_dt = start_dt
        end_dt = start_dt + datetime.timedelta(minutes=duration_min)
        
        while current_dt < end_dt:
            intervals.append(f"{current_dt.hour:02d}:{current_dt.minute:02d}:00")
            current_dt += datetime.timedelta(minutes=30)
        return set(intervals)
    except:
        return set()

# Sidebar loading configuration
st.sidebar.header("📂 Origen de Datos")
default_file_path = "08 Junio.xlsx"
archivo_excel = None

uploaded_file = st.sidebar.file_uploader("Carga el archivo Excel (ej. 08 Junio.xlsx)", type=['xlsx'])

if uploaded_file is not None:
    archivo_excel = uploaded_file
elif os.path.exists(default_file_path):
    archivo_excel = default_file_path
    st.sidebar.success(f"📂 Cargado por defecto: `{default_file_path}`")
else:
    st.sidebar.warning("Por favor carga un archivo WFM Excel en la barra lateral.")

if archivo_excel:
    try:
        @st.cache_data
        def cargar_y_procesar_crudo(file):
            xl = pd.ExcelFile(file)
            
            # Loading all 7 sheets
            df_staff = xl.parse('STAFF Total', skiprows=1)
            df_break = xl.parse('BREAK', skiprows=1)
            df_bano = xl.parse('BAÑO', skiprows=1)
            df_nov = xl.parse('Agen Novedades', skiprows=1)
            df_capa = xl.parse('CAPA', skiprows=1)
            df_ch = xl.parse('CH', skiprows=1)
            df_dec = xl.parse('Dev EC', skiprows=1)
            
            # Standardize columns to strip whitespaces and make them string
            for df in [df_staff, df_break, df_bano, df_nov, df_capa, df_ch, df_dec]:
                df.columns = [str(c).strip() for c in df.columns]
                
            # Clean empty rows
            if 'Asesor' in df_staff.columns: df_staff = df_staff.dropna(subset=['Asesor'])
            if 'Asesor' in df_break.columns: df_break = df_break.dropna(subset=['Asesor'])
            if 'Asesor' in df_bano.columns: df_bano = df_bano.dropna(subset=['Asesor'])
            if 'Asesor' in df_nov.columns: df_nov = df_nov.dropna(subset=['Asesor'])
            if 'Asesor' in df_capa.columns: df_capa = df_capa.dropna(subset=['Asesor'])
            if 'Asesor' in df_ch.columns: df_ch = df_ch.dropna(subset=['Asesor'])
            if 'Asesor' in df_dec.columns: df_dec = df_dec.dropna(subset=['Asesor'])
            
            # 1. Staff
            if 'Desvio' in df_staff.columns:
                df_staff['Es_Desviado'] = pd.to_numeric(df_staff['Desvio'], errors='coerce') == 1
                df_staff['Causa_Desvio'] = df_staff['Es_Desviado'].apply(lambda x: "Desvío de logueo (Staff)" if x else "OK")
            else:
                df_staff['Es_Desviado'] = False
                df_staff['Causa_Desvio'] = "Columna Desvio no encontrada"
                
            # 2. Break
            if 'Desvio' in df_break.columns:
                df_break['Es_Desviado'] = pd.to_numeric(df_break['Desvio'], errors='coerce') == 1
                df_break['Causa_Desvio'] = df_break['Es_Desviado'].apply(lambda x: "Desvío de Break" if x else "OK")
            else:
                df_break['Es_Desviado'] = False
                df_break['Causa_Desvio'] = "Columna Desvio no encontrada"
                
            # 3. Baño
            if 'ACUMULADO' in df_bano.columns:
                df_bano['Minutos_Bano'] = df_bano['ACUMULADO'].apply(convertir_a_minutos)
                df_bano['Es_Desviado'] = df_bano['Minutos_Bano'] > 10
                df_bano['Causa_Desvio'] = df_bano.apply(
                    lambda r: f"Exceso en baño ({r['Minutos_Bano']:.1f} min > 10 min)" if r['Es_Desviado'] else "OK", axis=1
                )
            else:
                df_bano['Es_Desviado'] = False
                df_bano['Causa_Desvio'] = "Columna ACUMULADO no encontrada"
                
            # 4. Novedades
            df_nov = procesar_desvio_generico(df_nov, "Novedad", check_schedule_shift=True)
            # 5. CAPA
            df_capa = procesar_desvio_generico(df_capa, "Capacitación", check_schedule_shift=False)
            # 6. Coaching
            df_ch = procesar_desvio_generico(df_ch, "Coaching", check_schedule_shift=True)
            # 7. Dev EC
            df_dec = procesar_desvio_generico(df_dec, "Error Crítico", check_schedule_shift=False)
            
            # Identify time interval columns
            time_cols = [c for c in df_staff.columns if ':' in c and len(c) <= 8]
            
            # Calculate frequency of bathroom and break uses for all advisors to rank them later
            df_bano['Frecuencia_Uso'] = df_bano.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            df_break['Frecuencia_Uso'] = df_break.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            df_nov['Frecuencia_Uso'] = df_nov.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            df_capa['Frecuencia_Uso'] = df_capa.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            df_ch['Frecuencia_Uso'] = df_ch.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            df_dec['Frecuencia_Uso'] = df_dec.apply(lambda r: contar_frecuencia_intervalos(r, time_cols), axis=1)
            
            return df_staff, df_break, df_bano, df_nov, df_capa, df_ch, df_dec
            
        with st.spinner("Procesando matriz de desvíos y convirtiendo tiempos..."):
            df_staff_raw, df_break_raw, df_bano_raw, df_nov_raw, df_capa_raw, df_ch_raw, df_dec_raw = cargar_y_procesar_crudo(archivo_excel)
            
        # Copy raw dataframes to apply sidebar filters
        df_staff = df_staff_raw.copy()
        df_break = df_break_raw.copy()
        df_bano = df_bano_raw.copy()
        df_nov = df_nov_raw.copy()
        df_capa = df_capa_raw.copy()
        df_ch = df_ch_raw.copy()
        df_dec = df_dec_raw.copy()
        
        # --- FILTROS GLOBALES (SIDEBAR - ORDEN ESTRICTO) ---
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Filtros de Segmentación")
        
        # 1. Filtro PROG SIMPLEX
        if 'PROG SIMPLEX' in df_staff.columns:
            simplex_list = sorted(df_staff['PROG SIMPLEX'].dropna().unique())
            selected_simplex = st.sidebar.multiselect("PROG SIMPLEX", options=simplex_list)
            if selected_simplex:
                df_staff = df_staff[df_staff['PROG SIMPLEX'].isin(selected_simplex)]
                df_break = df_break[df_break['PROG SIMPLEX'].isin(selected_simplex)]
                df_bano = df_bano[df_bano['PROG SIMPLEX'].isin(selected_simplex)]
                df_nov = df_nov[df_nov['PROG SIMPLEX'].isin(selected_simplex)]
                df_capa = df_capa[df_capa['PROG SIMPLEX'].isin(selected_simplex)]
                df_ch = df_ch[df_ch['PROG SIMPLEX'].isin(selected_simplex)]
                df_dec = df_dec[df_dec['PROG SIMPLEX'].isin(selected_simplex)]
                
        # 2. Filtro SKILL
        col_skill = 'SKILL' if 'SKILL' in df_staff.columns else ('PROG SIMPLEX' if 'PROG SIMPLEX' in df_staff.columns else None)
        if col_skill:
            skill_list = sorted(df_staff[col_skill].dropna().unique())
            selected_skills = st.sidebar.multiselect("Servicio / Skill", options=skill_list)
            if selected_skills:
                df_staff = df_staff[df_staff[col_skill].isin(selected_skills)]
                df_break = df_break[df_break[col_skill].isin(selected_skills)]
                df_bano = df_bano[df_bano[col_skill].isin(selected_skills)]
                df_nov = df_nov[df_nov[col_skill].isin(selected_skills)]
                df_capa = df_capa[df_capa[col_skill].isin(selected_skills)]
                df_ch = df_ch[df_ch[col_skill].isin(selected_skills)]
                df_dec = df_dec[df_dec[col_skill].isin(selected_skills)]
                
        # 3. Filtro PLATAFORMA
        if 'PLATAFORMA' in df_staff.columns:
            plataforma_list = sorted(df_staff['PLATAFORMA'].dropna().unique())
            selected_platforms = st.sidebar.multiselect("Plataforma", options=plataforma_list)
            if selected_platforms:
                df_staff = df_staff[df_staff['PLATAFORMA'].isin(selected_platforms)]
                df_break = df_break[df_break['PLATAFORMA'].isin(selected_platforms)]
                df_bano = df_bano[df_bano['PLATAFORMA'].isin(selected_platforms)]
                df_nov = df_nov[df_nov['PLATAFORMA'].isin(selected_platforms)]
                df_capa = df_capa[df_capa['PLATAFORMA'].isin(selected_platforms)]
                df_ch = df_ch[df_ch['PLATAFORMA'].isin(selected_platforms)]
                df_dec = df_dec[df_dec['PLATAFORMA'].isin(selected_platforms)]
                
        # 4. Filtro SUPERVISOR
        if 'SUPERVISOR' in df_staff.columns:
            supervisor_list = sorted(df_staff['SUPERVISOR'].dropna().unique())
            selected_supervisors = st.sidebar.multiselect("Supervisor", options=supervisor_list)
            if selected_supervisors:
                df_staff = df_staff[df_staff['SUPERVISOR'].isin(selected_supervisors)]
                df_break = df_break[df_break['SUPERVISOR'].isin(selected_supervisors)]
                df_bano = df_bano[df_bano['SUPERVISOR'].isin(selected_supervisors)]
                df_nov = df_nov[df_nov['SUPERVISOR'].isin(selected_supervisors)]
                df_capa = df_capa[df_capa['SUPERVISOR'].isin(selected_supervisors)]
                df_ch = df_ch[df_ch['SUPERVISOR'].isin(selected_supervisors)]
                df_dec = df_dec[df_dec['SUPERVISOR'].isin(selected_supervisors)]
                
        # Filtered Deviants Dataframes
        staff_desv = df_staff[df_staff['Es_Desviado'] == True]
        break_desv = df_break[df_break['Es_Desviado'] == True]
        bano_desv = df_bano[df_bano['Es_Desviado'] == True]
        nov_desv = df_nov[df_nov['Es_Desviado'] == True]
        capa_desv = df_capa[df_capa['Es_Desviado'] == True]
        ch_desv = df_ch[df_ch['Es_Desviado'] == True]
        dec_desv = df_dec[df_dec['Es_Desviado'] == True]
        
        # --- SANITIZE DATAFRAMES TO STRING TO PREVENT PYARROW ERRORS ---
        def sanitizar_df_para_arrow(df):
            df_clean = df.copy()
            for col in df_clean.columns:
                if col not in ['Es_Desviado', 'Minutos_Bano', 'Minutos', 'Frecuencia_Uso']:
                    df_clean[col] = df_clean[col].apply(lambda x: '' if pd.isna(x) else str(x).strip())
            return df_clean
            
        staff_show = sanitizar_df_para_arrow(df_staff)
        break_show = sanitizar_df_para_arrow(df_break)
        bano_show = sanitizar_df_para_arrow(df_bano)
        nov_show = sanitizar_df_para_arrow(df_nov)
        capa_show = sanitizar_df_para_arrow(df_capa)
        ch_show = sanitizar_df_para_arrow(df_ch)
        dec_show = sanitizar_df_para_arrow(df_dec)
        
        staff_desv_show = staff_show[staff_show['Es_Desviado'] == True]
        break_desv_show = break_show[break_show['Es_Desviado'] == True]
        bano_desv_show = bano_show[bano_show['Es_Desviado'] == True]
        nov_desv_show = nov_show[nov_show['Es_Desviado'] == True]
        capa_desv_show = capa_show[capa_show['Es_Desviado'] == True]
        ch_desv_show = ch_show[ch_show['Es_Desviado'] == True]
        dec_desv_show = dec_show[dec_show['Es_Desviado'] == True]
        
        # --- TAB CONTROLLER ---
        tab_kpi, tab_supervisor, tab_clinico, tab_listados = st.tabs([
            "📊 Resumen de Impacto", 
            "👥 Control por Supervisor",
            "🔎 Radiografía por Asesor",
            "📋 Listados de Acción"
        ])
        
        # ========================================================
        # TAB 1: RESUMEN Y CURVAS (IMPACTO)
        # ========================================================
        with tab_kpi:
            st.markdown("### 📈 Indicadores de Adherencia y Desvíos (Visión Macro)")
            
            # 1. Concept filtering multiselect
            conceptos_disponibles = {
                "Staff Logueo": "Staff",
                "Break": "Break",
                "Baño": "Baño",
                "Novedades": "Novedades",
                "Capacitación (CAPA)": "Capacitación",
                "Coaching (CH)": "Coaching",
                "Error Crítico (Dev EC)": "Error Crítico"
            }
            
            selected_concepts = st.multiselect(
                "Filtrar conceptos en las gráficas consolidadas y tablas de peso porcentual:",
                options=list(conceptos_disponibles.keys()),
                default=list(conceptos_disponibles.keys()),
                key="tab_kpi_conceptos_multiselect"
            )
            
            # Cards showing all concepts (always showing all for completeness, with highlight on deviations)
            c0, c1, c2, c3, c4, c5, c6, c7 = st.columns(8)
            total_asesores = df_staff['Asesor'].nunique()
            
            with c0:
                render_kpi_card("Total Asesores", f"{total_asesores}", is_deviated=False, subtitle="Plantilla auditada")
            with c1:
                render_kpi_card("Desvíos Staff", f"{len(staff_desv)}", is_deviated=len(staff_desv) > 0, 
                                subtitle=f"{(len(staff_desv)/max(1, len(df_staff))*100):.1f}% de tasa")
            with c2:
                render_kpi_card("Desvíos Break", f"{len(break_desv)}", is_deviated=len(break_desv) > 0, 
                                subtitle=f"{(len(break_desv)/max(1, len(df_break))*100):.1f}% de tasa")
            with c3:
                render_kpi_card("Exceso Baño", f"{len(bano_desv)}", is_deviated=len(bano_desv) > 0, 
                                subtitle=f"Exceden >10 min")
            with c4:
                render_kpi_card("Desvíos Novedades", f"{len(nov_desv)}", is_deviated=len(nov_desv) > 0, 
                                subtitle=f"{(len(nov_desv)/max(1, len(df_nov))*100):.1f}% de tasa")
            with c5:
                render_kpi_card("Desvíos Capa", f"{len(capa_desv)}", is_deviated=len(capa_desv) > 0, 
                                subtitle=f"{(len(capa_desv)/max(1, len(df_capa))*100):.1f}% de tasa")
            with c6:
                render_kpi_card("Desvíos Coaching", f"{len(ch_desv)}", is_deviated=len(ch_desv) > 0, 
                                subtitle=f"{(len(ch_desv)/max(1, len(df_ch))*100):.1f}% de tasa")
            with c7:
                render_kpi_card("Desvíos Err.Crítico", f"{len(dec_desv)}", is_deviated=len(dec_desv) > 0, 
                                subtitle=f"{(len(dec_desv)/max(1, len(df_dec))*100):.1f}% de tasa")
            
            st.markdown("---")
            
            # Helper to retrieve deviations filtered by selected concepts
            def get_consolidated_deviations(col_name, selected_keys):
                records = []
                sheets_dict = {
                    "Staff": df_staff, "Break": df_break, "Baño": df_bano,
                    "Novedades": df_nov, "Capacitación": df_capa, "Coaching": df_ch,
                    "Error Crítico": df_dec
                }
                selected_short_keys = [conceptos_disponibles[k] for k in selected_keys]
                
                for name, df_s in sheets_dict.items():
                    if name in selected_short_keys:
                        if not df_s.empty and col_name in df_s.columns:
                            counts = df_s[df_s['Es_Desviado'] == True][col_name].value_counts()
                            for val, count in counts.items():
                                records.append({"Componente": val, "Concepto": name, "Desvíos": count})
                return pd.DataFrame(records) if records else pd.DataFrame(columns=["Componente", "Concepto", "Desvíos"])
            
            if selected_concepts:
                # --- 1. PROG SIMPLEX METRICS ---
                st.markdown('<p class="section-title">📊 Distribución de Desvíos por PROG SIMPLEX</p>', unsafe_allow_html=True)
                df_res_simplex = get_consolidated_deviations('PROG SIMPLEX', selected_concepts)
                
                if not df_res_simplex.empty:
                    col_chart, col_table = st.columns([2, 1])
                    with col_chart:
                        fig_simplex = px.bar(
                            df_res_simplex, x='Componente', y='Desvíos', color='Concepto',
                            title="Desvíos Acumulados por PROG SIMPLEX (Filtrados)", barmode='stack',
                            color_discrete_map={
                                'Staff': '#EF4444', 'Break': '#F59E0B', 'Baño': '#10B981', 
                                'Novedades': '#3B82F6', 'Capacitación': '#8B5CF6', 
                                'Coaching': '#EC4899', 'Error Crítico': '#6366F1'
                            }
                        )
                        fig_simplex.update_layout(xaxis_title="PROG SIMPLEX", yaxis_title="Desvíos", height=400)
                        st.plotly_chart(fig_simplex, use_container_width=True)
                    with col_table:
                        df_weight = df_res_simplex.groupby('Componente')['Desvíos'].sum().reset_index()
                        total_d = df_weight['Desvíos'].sum()
                        df_weight['% Peso'] = (df_weight['Desvíos'] / max(1, total_d) * 100).round(1)
                        df_weight = df_weight.sort_values(by='Desvíos', ascending=False)
                        st.write("**Desglose y Peso Porcentual**")
                        st.dataframe(df_weight.reset_index(drop=True), width=400)
                else:
                    st.write("No hay desvíos registrados por PROG SIMPLEX con los filtros seleccionados.")
                    
                st.markdown("---")
                
                # --- 2. PLATAFORMA METRICS ---
                st.markdown('<p class="section-title">🏢 Distribución de Desvíos por Plataforma / Sitio</p>', unsafe_allow_html=True)
                df_res_plat = get_consolidated_deviations('PLATAFORMA', selected_concepts)
                
                if not df_res_plat.empty:
                    col_chart, col_table = st.columns([2, 1])
                    with col_chart:
                        fig_plat = px.bar(
                            df_res_plat, x='Componente', y='Desvíos', color='Concepto',
                            title="Desvíos Acumulados por Plataforma (Filtrados)", barmode='stack',
                            color_discrete_map={
                                'Staff': '#EF4444', 'Break': '#F59E0B', 'Baño': '#10B981', 
                                'Novedades': '#3B82F6', 'Capacitación': '#8B5CF6', 
                                'Coaching': '#EC4899', 'Error Crítico': '#6366F1'
                            }
                        )
                        fig_plat.update_layout(xaxis_title="Plataforma", yaxis_title="Desvíos", height=400)
                        st.plotly_chart(fig_plat, use_container_width=True)
                    with col_table:
                        df_weight = df_res_plat.groupby('Componente')['Desvíos'].sum().reset_index()
                        total_d = df_weight['Desvíos'].sum()
                        df_weight['% Peso'] = (df_weight['Desvíos'] / max(1, total_d) * 100).round(1)
                        df_weight = df_weight.sort_values(by='Desvíos', ascending=False)
                        st.write("**Desglose y Peso Porcentual**")
                        st.dataframe(df_weight.reset_index(drop=True), width=400)
                else:
                    st.write("No hay desvíos registrados por Plataforma con los filtros seleccionados.")
                    
                st.markdown("---")
                
                # --- 3. SUPERVISOR METRICS ---
                st.markdown('<p class="section-title">👥 Distribución de Desvíos por Supervisor (Líder)</p>', unsafe_allow_html=True)
                df_res_sup = get_consolidated_deviations('SUPERVISOR', selected_concepts)
                
                if not df_res_sup.empty:
                    col_chart, col_table = st.columns([2, 1])
                    with col_chart:
                        fig_sup = px.bar(
                            df_res_sup, x='Componente', y='Desvíos', color='Concepto',
                            title="Desvíos Acumulados por Supervisor (Filtrados)", barmode='stack',
                            color_discrete_map={
                                'Staff': '#EF4444', 'Break': '#F59E0B', 'Baño': '#10B981', 
                                'Novedades': '#3B82F6', 'Capacitación': '#8B5CF6', 
                                'Coaching': '#EC4899', 'Error Crítico': '#6366F1'
                            }
                        )
                        fig_sup.update_layout(xaxis_title="Supervisor", yaxis_title="Desvíos", height=450)
                        st.plotly_chart(fig_sup, use_container_width=True)
                    with col_table:
                        df_weight = df_res_sup.groupby('Componente')['Desvíos'].sum().reset_index()
                        total_d = df_weight['Desvíos'].sum()
                        df_weight['% Peso'] = (df_weight['Desvíos'] / max(1, total_d) * 100).round(1)
                        df_weight = df_weight.sort_values(by='Desvíos', ascending=False)
                        st.write("**Desglose y Peso Porcentual**")
                        st.dataframe(df_weight.reset_index(drop=True), width=400)
                else:
                    st.write("No hay desvíos registrados por Supervisor con los filtros seleccionados.")
            else:
                st.info("💡 Selecciona al menos un concepto en la parte superior para visualizar las métricas consolidadas.")
                
            st.markdown("---")
            
            # --- Worst Offenders ranking ---
            st.markdown('<p class="section-title">🚨 Top 10 Agentes con Mayor Frecuencia y Tiempo de Desvío</p>', unsafe_allow_html=True)
            t_col1, t_col2 = st.columns(2)
            
            with t_col1:
                st.markdown("#### 🚹 Exceso en Baño (Top 10 por Tiempo)")
                top_bano = df_bano.sort_values(by='Minutos_Bano', ascending=False).head(10)
                cols_bano = ['ID', 'Asesor', 'SUPERVISOR', 'ACUMULADO', 'Frecuencia_Uso']
                st.dataframe(sanitizar_df_para_arrow(top_bano)[cols_bano].reset_index(drop=True), use_container_width=True)
                
            with t_col2:
                st.markdown("#### ☕ Exceso en Break (Top 10 por Frecuencia de Uso)")
                top_break = df_break[df_break['Es_Desviado'] == True].sort_values(by='Frecuencia_Uso', ascending=False).head(10)
                cols_brk = ['ID', 'Asesor', 'SUPERVISOR', 'BREAK PROG', 'BREAK Real', 'Frecuencia_Uso']
                st.dataframe(sanitizar_df_para_arrow(top_break)[cols_brk].reset_index(drop=True), use_container_width=True)
                
        # ========================================================
        # TAB 2: CONTROL POR SUPERVISOR
        # ========================================================
        with tab_supervisor:
            st.markdown("### 👥 Control y Auditoría por Líder")
            st.write("Audita los patrones de comportamiento, mapas de calor comparativos de Programado vs Real y la frecuencia de uso:")
            
            if 'SUPERVISOR' in df_staff.columns:
                lista_supervisores = sorted(df_staff['SUPERVISOR'].dropna().unique())
                sup_sel = st.selectbox("Selecciona un Supervisor para auditar:", options=lista_supervisores, key="control_sup_sel")
                concepto_sel = st.selectbox(
                    "Selecciona el Concepto a analizar en el mapa de calor:", 
                    ["Staff Logueo", "Break", "Baño", "Novedades", "Capacitación (CAPA)", "Coaching (CH)", "Error Crítico (Dev EC)"],
                    key="control_concept_sel"
                )
                
                # Filter sheets for supervisor
                df_staff_sup = df_staff[df_staff['SUPERVISOR'] == sup_sel]
                df_break_sup = df_break[df_break['SUPERVISOR'] == sup_sel]
                df_bano_sup = df_bano[df_bano['SUPERVISOR'] == sup_sel]
                df_nov_sup = df_nov[df_nov['SUPERVISOR'] == sup_sel]
                df_capa_sup = df_capa[df_capa['SUPERVISOR'] == sup_sel]
                df_ch_sup = df_ch[df_ch['SUPERVISOR'] == sup_sel]
                df_dec_sup = df_dec[df_dec['SUPERVISOR'] == sup_sel]
                
                target_df_sup = {
                    "Staff Logueo": df_staff_sup, "Break": df_break_sup, "Baño": df_bano_sup,
                    "Novedades": df_nov_sup, "Capacitación (CAPA)": df_capa_sup,
                    "Coaching (CH)": df_ch_sup, "Error Crítico (Dev EC)": df_dec_sup
                }[concepto_sel]
                
                if not target_df_sup.empty:
                    st.write(f"Asesores en el equipo de **{sup_sel}**: `{len(target_df_sup)}` asesores.")
                    
                    time_cols = [c for c in target_df_sup.columns if ':' in c and len(c) <= 8]
                    
                    # --- Heatmap construction (Consolidated single-row) ---
                    heatmap_data = []
                    
                    for idx, row in target_df_sup.sort_values(by="Asesor").iterrows():
                        row_data = {"Asesor": row['Asesor']}
                        
                        # 1. Determine programmed intervals for this advisor
                        prog_intervals = set()
                        if concepto_sel == "Staff Logueo":
                            start_time = str(row.get('Horario PROG', '00:00:00')).strip()
                            dur = row.get('HS de Gestion', '6')
                            if str(dur).strip() in ['', '-', 'nan']:
                                dur = 6.0
                            try:
                                dur = float(str(dur).replace(',', '.'))
                            except:
                                dur = 6.0
                            prog_intervals = obtener_rango_horas(start_time, dur)
                        elif concepto_sel == "Break":
                            brk_prog = str(row.get('BREAK PROG', '00:00:00')).strip()
                            if brk_prog != '00:00:00' and brk_prog != '-' and brk_prog != '':
                                prog_intervals = {brk_prog}
                        elif concepto_sel in ["Novedades", "Capacitación (CAPA)", "Coaching (CH)", "Error Crítico (Dev EC)"]:
                            prog_val = str(row.get('PROGRAMADO', '00:00:00')).strip()
                            if prog_val != '00:00:00' and prog_val != '-' and prog_val != '':
                                prog_intervals = {prog_val}
                        
                        # 2. Loop through all 48 time intervals
                        for col in time_cols:
                            is_prog = (col in prog_intervals)
                            minutes = convertir_a_minutos(row[col])
                            is_real = (minutes > 0)
                            
                            if concepto_sel == "Baño":
                                if is_real:
                                    is_agent_dev = row.get('Es_Desviado', False)
                                    row_data[col] = 2.0 if is_agent_dev else 1.0
                                else:
                                    row_data[col] = 0.0
                            else:
                                if not is_prog and not is_real:
                                    row_data[col] = 0.0 # White/Transparent
                                elif is_prog and is_real:
                                    row_data[col] = 1.0 # Light Green (Adherent)
                                else:
                                    row_data[col] = 2.0 # Light Red (Deviation)
                                    
                        heatmap_data.append(row_data)
                        
                    df_heatmap = pd.DataFrame(heatmap_data).set_index("Asesor")
                    
                    # Custom discrete colorscale: 0=transparent, 1=light green, 2=light red
                    colorscale = [
                        [0.0, 'rgba(255, 255, 255, 0.0)'],  # 0 maps to transparent white
                        [0.33, 'rgba(255, 255, 255, 0.0)'],
                        [0.33, 'rgba(165, 243, 204, 0.9)'], # 1 maps to light green (Adherent)
                        [0.66, 'rgba(165, 243, 204, 0.9)'],
                        [0.66, 'rgba(254, 178, 178, 0.9)'], # 2 maps to light red (Desviado)
                        [1.0, 'rgba(254, 178, 178, 0.9)']
                    ]
                    
                    # Hover info
                    hover_text = []
                    for idx, row in df_heatmap.iterrows():
                        row_hover = []
                        for col in df_heatmap.columns:
                            val = row[col]
                            if val == 0.0:
                                state_str = "Inactivo (Sin programar y sin realizar)"
                            elif val == 1.0:
                                state_str = "Adherente (Programado y realizado, o ambos inactivos)"
                            else:
                                state_str = "Desviado (Diferencia entre programación y realización)"
                            row_hover.append(state_str)
                        hover_text.append(row_hover)
                    
                    fig_heat = px.imshow(
                        df_heatmap,
                        labels=dict(x="Hora del Día", y="Asesor", color="Estado"),
                        x=df_heatmap.columns,
                        y=df_heatmap.index,
                        color_continuous_scale=colorscale,
                        zmin=0,
                        zmax=2,
                        title=f"Mapa de Calor de Adherencia Clínica (1 Fila/Asesor) - {concepto_sel}"
                    )
                    fig_heat.update_traces(
                        customdata=hover_text,
                        hovertemplate="<b>Asesor:</b> %{y}<br><b>Intervalo:</b> %{x}<br><b>Estado:</b> %{customdata}<extra></extra>"
                    )
                    fig_heat.update_layout(
                        height=160 + len(df_heatmap) * 22,
                        xaxis=dict(title="Intervalo", tickangle=-45),
                        coloraxis_showscale=False # Hide colorbar
                    )
                    st.plotly_chart(fig_heat, use_container_width=True)
                    
                    st.markdown("---")
                    st.markdown("#### 📊 Comparativa de Uso del Concepto (Frecuencia vs Tiempo Acumulado)")
                    
                    # Freq vs Time list
                    freq_time_list = []
                    for idx, row in target_df_sup.iterrows():
                        if concepto_sel == "Baño":
                            tot_min = row.get('Minutos_Bano', 0.0)
                        else:
                            tot_min = convertir_a_minutos(row.get('ACUMULADO', 0.0))
                            
                        freq = row.get('Frecuencia_Uso', 0)
                        freq_time_list.append({
                            "Asesor": row['Asesor'],
                            "Tiempo Total (min)": tot_min,
                            "Frecuencia (Intervalos)": freq
                        })
                    df_freq_time = pd.DataFrame(freq_time_list).sort_values(by="Tiempo Total (min)", ascending=False)
                    
                    # Double bar chart
                    fig_compare = go.Figure()
                    fig_compare.add_trace(go.Bar(
                        x=df_freq_time['Asesor'], y=df_freq_time['Tiempo Total (min)'],
                        name='Tiempo Acumulado (min)', marker_color='#3B82F6'
                    ))
                    fig_compare.add_trace(go.Bar(
                        x=df_freq_time['Asesor'], y=df_freq_time['Frecuencia (Intervalos)'],
                        name='Frecuencia (Cantidad de Bloques)', marker_color='#F59E0B'
                    ))
                    fig_compare.update_layout(
                        barmode='group', xaxis_title="Asesor", yaxis_title="Valor",
                        legend_title="Métrica", height=400
                    )
                    st.plotly_chart(fig_compare, use_container_width=True)
                else:
                    st.write("No hay información de intervalos para este equipo en el concepto seleccionado.")
            else:
                st.warning("Columna SUPERVISOR no encontrada en los datos.")
                
        # ========================================================
        # TAB 3: RADIOGRAFÍA CLÍNICA POR ASESOR (CASCADA / SCROLL)
        # ========================================================
        with tab_clinico:
            st.markdown("### 🔬 Diagnóstico Clínico de Asesores en Cascada")
            st.write("Inspecciona la jornada, tarjetas HSL de adherencia y líneas de tiempo Gantt en un scroll vertical continuo:")
            
            col_sc1, col_sc2, col_sc3 = st.columns(3)
            
            with col_sc1:
                lider_sel = st.selectbox(
                    "Filtra todos los agentes de un Supervisor / Líder:", 
                    options=["-- Ver Todos --"] + sorted(df_staff['SUPERVISOR'].dropna().unique()),
                    key="diagnostico_lider_sel"
                )
            with col_sc2:
                buscar_nombre = st.text_input("🔍 Buscar Asesor por Nombre:", key="diagnostico_nombre_sel")
            with col_sc3:
                buscar_dni = st.text_input("🔍 Buscar por DNI:", key="diagnostico_dni_sel")
                
            # Filter the list of advisors based on selections
            df_filtered_asesores = df_staff.copy()
            if lider_sel != "-- Ver Todos --":
                df_filtered_asesores = df_filtered_asesores[df_filtered_asesores['SUPERVISOR'] == lider_sel]
            if buscar_nombre:
                df_filtered_asesores = df_filtered_asesores[df_filtered_asesores['Asesor'].str.contains(buscar_nombre, case=False, na=False)]
            if buscar_dni:
                df_filtered_asesores = df_filtered_asesores[df_filtered_asesores['DNI'].astype(str).str.contains(buscar_dni, na=False)]
                
            lista_asesores_filtrada = sorted(df_filtered_asesores['Asesor'].dropna().unique())
            
            if len(lista_asesores_filtrada) > 30 and (lider_sel == "-- Ver Todos --" and not buscar_nombre and not buscar_dni):
                st.warning(f"⚠️ Hay {len(lista_asesores_filtrada)} asesores seleccionados. Para evitar congelar el navegador, por favor filtra por Supervisor o escribe en las cajas de búsqueda. (Mostrando un máximo de 10 por seguridad hasta que filtres)")
                lista_asesores_filtrada = lista_asesores_filtrada[:10]
                
            st.write(f"Mostrando **{len(lista_asesores_filtrada)}** diagnósticos detallados en cascada:")
            
            for idx_a, asesor_sel in enumerate(lista_asesores_filtrada):
                st.markdown(f"""
                <div style="border-top: 3px solid #1E3A8A; margin-top: 40px; padding-top: 15px;">
                    <span style="font-size: 20px; font-weight: 800; color: #1E3A8A;">👤 #{idx_a + 1}: {asesor_sel}</span>
                </div>
                """, unsafe_allow_html=True)
                
                # Query advisor rows in each sheet
                a_staff = df_staff[df_staff['Asesor'] == asesor_sel]
                a_break = df_break[df_break['Asesor'] == asesor_sel]
                a_bano = df_bano[df_bano['Asesor'] == asesor_sel]
                a_nov = df_nov[df_nov['Asesor'] == asesor_sel]
                a_capa = df_capa[df_capa['Asesor'] == asesor_sel]
                a_ch = df_ch[df_ch['Asesor'] == asesor_sel]
                a_dec = df_dec[df_dec['Asesor'] == asesor_sel]
                
                if not a_staff.empty:
                    st.write(f"**Supervisor:** `{a_staff['SUPERVISOR'].values[0]}` | **Plataforma:** `{a_staff['PLATAFORMA'].values[0]}` | **Skill:** `{a_staff[col_skill].values[0]}`")
                
                k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
                
                # 1. Staff Card
                with k1:
                    if not a_staff.empty:
                        dev = a_staff['Es_Desviado'].values[0]
                        prog = a_staff['Horario PROG'].values[0]
                        real = a_staff['Horario Log'].values[0]
                        render_kpi_card("1. Staff Logueo", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {real}")
                    else:
                        render_kpi_card("1. Staff Logueo", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 2. Break Card
                with k2:
                    if not a_break.empty:
                        dev = a_break['Es_Desviado'].values[0]
                        prog = a_break['BREAK PROG'].values[0]
                        real = a_break['BREAK Real'].values[0]
                        render_kpi_card("2. Break", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {real}")
                    else:
                        render_kpi_card("2. Break", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 3. Baño Card
                with k3:
                    if not a_bano.empty:
                        dev = a_bano['Es_Desviado'].values[0]
                        acum = a_bano['ACUMULADO'].values[0]
                        render_kpi_card("3. Baño", f"{acum}", is_deviated=dev, subtitle="Límite: 10 min máx")
                    else:
                        render_kpi_card("3. Baño", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 4. Novedades Card
                with k4:
                    if not a_nov.empty:
                        dev = a_nov['Es_Desviado'].values[0]
                        prog = a_nov['PROGRAMADO'].values[0]
                        acum = a_nov['ACUMULADO'].values[0]
                        render_kpi_card("4. Novedades", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {acum}")
                    else:
                        render_kpi_card("4. Novedades", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 5. Capa Card
                with k5:
                    if not a_capa.empty:
                        dev = a_capa['Es_Desviado'].values[0]
                        prog = a_capa['PROGRAMADO'].values[0]
                        acum = a_capa['ACUMULADO'].values[0]
                        render_kpi_card("5. Capacitación", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {acum}")
                    else:
                        render_kpi_card("5. Capacitación", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 6. Coaching Card
                with k6:
                    if not a_ch.empty:
                        dev = a_ch['Es_Desviado'].values[0]
                        prog = a_ch['PROGRAMADO'].values[0]
                        acum = a_ch['ACUMULADO'].values[0]
                        render_kpi_card("6. Coaching", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {acum}")
                    else:
                        render_kpi_card("6. Coaching", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                        
                # 7. Dev EC Card
                with k7:
                    if not a_dec.empty:
                        dev = a_dec['Es_Desviado'].values[0]
                        prog = a_dec['PROGRAMADO'].values[0]
                        acum = a_dec['ACUMULADO'].values[0]
                        render_kpi_card("7. Error Crítico", "🚨 DESVIADO" if dev else "✅ OK", is_deviated=dev, subtitle=f"Prog: {prog} | Real: {acum}")
                    else:
                        render_kpi_card("7. Error Crítico", "⚪ N/A", is_deviated=False, subtitle="Sin registro")
                
                # Report on reasons for deviations if any
                deviation_reasons = []
                for label, ad_df in [
                    ("Staff", a_staff), ("Break", a_break), ("Baño", a_bano), 
                    ("Novedades", a_nov), ("Capacitación", a_capa), 
                    ("Coaching", a_ch), ("Dev EC", a_dec)
                ]:
                    if not ad_df.empty and ad_df['Es_Desviado'].values[0]:
                        reason = ad_df['Causa_Desvio'].values[0]
                        deviation_reasons.append(f"- **{label}:** {reason}")
                
                if deviation_reasons:
                    st.error(f"Hallazgos para **{asesor_sel}**:\n" + "\n".join(deviation_reasons))
                else:
                    st.success(f"Asesor **{asesor_sel}** libre de desvíos en todas las métricas.")
                    
                # --- TIMELINE FOR SCROLL ---
                timeline_data = []
                activities = {
                    "1. Staff Logueo": a_staff, "2. Break": a_break, "3. Baño": a_bano,
                    "4. Novedades": a_nov, "5. Capacitación": a_capa, "6. Coaching": a_ch,
                    "7. Error Crítico": a_dec
                }
                
                for act_name, act_df in activities.items():
                    if not act_df.empty:
                        row = act_df.iloc[0]
                        for col in act_df.columns:
                            if ':' in col and len(col) <= 8:
                                val = row[col]
                                minutes = convertir_a_minutos(val)
                                if minutes > 0:
                                    start_str = col[:5]
                                    try:
                                        parts = col.split(':')
                                        h, m = int(parts[0]), int(parts[1])
                                        m_end = m + 30
                                        h_end = h
                                        if m_end >= 60:
                                            m_end -= 60
                                            h_end = (h_end + 1) % 24
                                        end_str = f"{h_end:02d}:{m_end:02d}"
                                    except:
                                        end_str = start_str
                                    
                                    timeline_data.append({
                                        "Actividad": act_name,
                                        "Inicio": f"2026-06-08 {start_str}:00",
                                        "Fin": f"2026-06-08 {end_str}:00",
                                        "Minutos": minutes,
                                        "Intervalo": col
                                    })
                
                if timeline_data:
                    df_timeline = pd.DataFrame(timeline_data)
                    fig_timeline = px.timeline(
                        df_timeline, x_start="Inicio", x_end="Fin", y="Actividad", color="Actividad",
                        hover_data={"Inicio": False, "Fin": False, "Minutos": True, "Intervalo": True},
                        color_discrete_map={
                            "1. Staff Logueo": '#EF4444', "2. Break": '#F59E0B', "3. Baño": '#10B981', 
                            "4. Novedades": '#3B82F6', "5. Capacitación": '#8B5CF6', 
                            "6. Coaching": '#EC4899', "7. Error Crítico": '#6366F1'
                        }
                    )
                    fig_timeline.update_layout(
                        xaxis=dict(title="Intervalo (Hora del Día)", tickformat="%H:%M", type="date"),
                        yaxis=dict(title="", autorange="reversed"),
                        showlegend=False, height=180, margin=dict(t=5, b=5)
                    )
                    st.plotly_chart(fig_timeline, use_container_width=True)
                else:
                    st.info("No se registraron tiempos en los intervalos para este asesor.")
                    
        # ========================================================
        # TAB 4: LISTADOS DE ACCIÓN (HITLIST)
        # ========================================================
        with tab_listados:
            st.markdown("### 📋 Listas de Acción por Métrica")
            
            opcion_desvio = st.selectbox(
                "Selecciona el tipo de desvío a auditar:", 
                ["🚨 Staff Logueo", "☕ Break", "🚹 Baño", "📅 Agen Novedades", "📚 Capacitación (CAPA)", "🎯 Coaching (CH)", "⚠️ Devolución Error Crítico (Dev EC)"],
                key="listados_hitlist"
            )
            
            # Map choice to correct df
            if opcion_desvio == "🚨 Staff Logueo":
                target_df = staff_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'Horario PROG', 'Horario Log', 'Causa_Desvio']
            elif opcion_desvio == "☕ Break":
                target_df = break_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'BREAK PROG', 'BREAK Real', 'ACUMULADO', 'Causa_Desvio']
            elif opcion_desvio == "🚹 Baño":
                target_df = bano_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'ACUMULADO', 'Minutos_Bano', 'Causa_Desvio']
            elif opcion_desvio == "📅 Agen Novedades":
                target_df = nov_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'PROGRAMADO', 'ACUMULADO', 'Causa_Desvio']
            elif opcion_desvio == "📚 Capacitación (CAPA)":
                target_df = capa_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'PROGRAMADO', 'ACUMULADO', 'Causa_Desvio']
            elif opcion_desvio == "🎯 Coaching (CH)":
                target_df = ch_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'PROGRAMADO', 'ACUMULADO', 'Causa_Desvio']
            else: # Dev EC
                target_df = dec_desv_show
                cols_to_show = ['ID', 'Asesor', 'SUPERVISOR', 'PLATAFORMA', col_skill, 'PROGRAMADO', 'ACUMULADO', 'Causa_Desvio']
                
            cols_clean = [c for c in cols_to_show if c in target_df.columns]
            
            st.write(f"**Asesores con desvío detectado: {len(target_df)}**")
            st.dataframe(target_df[cols_clean].reset_index(drop=True), use_container_width=True)
            
    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
        st.exception(e)