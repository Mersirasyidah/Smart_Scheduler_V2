if uploaded_file is not None:
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        sheets = [s.strip() for s in excel_file.sheet_names]

        def read_clean(sheet_name):
            df = pd.read_excel(excel_file, sheet_name)
            df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
            return df

        guru_df = read_clean("Guru")
        rombel_df = read_clean("Rombel" if "Rombel" in sheets else "Kelas")

        mengajar_sheet = (
            "Guru_Mengajar" if "Guru_Mengajar" in sheets else "Mengajar"
        )
        mengajar_df = read_clean(mengajar_sheet)

        mapel_df = read_clean("Mapel")

        slot_sheet = "Hari_Jam" if "Hari_Jam" in sheets else "Slot"
        slot_df = read_clean(slot_sheet)

        scheduler_data = SchedulerData(
            guru_df, rombel_df, mengajar_df, mapel_df, slot_df
        )
        st.sidebar.success("✅ File Excel unggahan berhasil dibaca!")
    except Exception as e:
        st.sidebar.error(f"❌ Error membaca file upload: {e}")
