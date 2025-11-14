    """
    从CSV加载最后的CVD值（如果足够新）。针对大文件进行了优化。
    """
    if not os.path.exists(csv_file_path):
        logger.info(f"没有找到现有的CSV文件: {csv_file_path}。将从0开始CVD计算。")
        return 0.0

    try:
        # 获取文件大小和修改时间
        file_size = os.path.getsize(csv_file_path)
        file_mtime = os.path.getmtime(csv_file_path)
        file_mtime_dt = datetime.fromtimestamp(file_mtime)
        now = datetime.now()

        # 检查文件是否太旧
        if (now - file_mtime_dt).days > max_age_days:
            logger.info(f"CSV文件 {csv_file_path} 太旧（{(now - file_mtime_dt).days} 天）。将从0开始CVD计算。")
            return 0.0

        # 如果文件为空，返回0
        if file_size == 0:
            logger.warning(f"CSV文件 {csv_file_path} 为空。将从0开始CVD计算。")
            return 0.0

        # 检查文件是否太小（只有标题行）
        if file_size < 100:  # 假设标题行小于100字节
            with open(csv_file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                row_count = sum(1 for _ in reader)
                if row_count <= 1:  # 只有标题行
                    logger.info(f"CSV文件 {csv_file_path} 只包含标题行。将从0开始CVD计算。")
                    return 0.0

        # 对于大文件，只读取最后几行
        last_line = ""
        chunk_size = min(file_size, 4096)  # 读取最后4KB或整个文件
        
        with open(csv_file_path, 'rb') as f:
            # 移动到文件末尾前的chunk_size字节
            f.seek(-chunk_size, 2)
            # 读取最后的chunk
            last_chunk = f.read().decode('utf-8', errors='ignore')
            # 分割成行并获取最后一行
            lines = last_chunk.splitlines()
            if lines:
                last_line = lines[-1]

        # 如果找到最后一行，解析它
        if last_line:
            try:
                # 假设CSV格式为: timestamp,price,cvd,volume
                parts = last_line.split(',')
                if len(parts) >= 3:
                    last_cvd = float(parts[2])
                    logger.info(f"从CSV文件 {csv_file_path} 加载了最后的CVD值: {last_cvd}")
                    return last_cvd
            except (ValueError, IndexError) as e:
                logger.warning(f"解析CSV文件 {csv_file_path} 的最后一行时出错: {e}。将从0开始CVD计算。")

        return 0.0
    except Exception as e:
        logger.error(f"从CSV文件 {csv_file_path} 加载CVD时发生错误: {e}。将从0开始CVD计算。")
        return 0.0