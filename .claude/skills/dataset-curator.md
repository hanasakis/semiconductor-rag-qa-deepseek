---
name: dataset-curator
description: SECOM 制程数据整理、缺失值检测、数据字典生成、异常传感器标注
model: deepseek-v4-flash
---

# Dataset Curator — SECOM 数据整理技能

## 用途
对半导体 SECOM 制程数据集进行标准化整理、质量检查和元数据生成，为后续异常分析提供干净的数据基础。

## 工作流程

### 1. 数据加载
- 从 `data/sample/` 或 `data/raw/` 加载 SECOM CSV/Parquet 文件
- 自动识别列名：Sensor_XXX (传感器), Time (时间戳), Lot/Wafer/Die (层级标识)
- 输出 DataFrame 基本信息：行数、列数、内存占用

### 2. 缺失值分析
对每一列输出：
```
列名          缺失数    缺失率%    建议
Sensor_V1     12        0.8%      均值填充 (正态分布)
Sensor_V42    156       10.4%     标记为 NA_FLAG 列
Lot_ID        0         0.0%       无缺失
```
判断标准：
- <1% 缺失 → 均值/中位数填充
- 1%~5% 缺失 → 多重插补或多重填充策略
- 5%~20% 缺失 → 创建 NA_FLAG 标记列 + 填充
- >20% 缺失 → 建议剔除该列或作为独立分析维度
- >50% 缺失 → 自动剔除并标注 WARN

### 3. 数据字典生成
为每一列生成：
```yaml
Sensor_V1:
  type: float64
  description: "Etch chamber pressure sensor (推测)"
  unit: "mTorr"
  min: 0.0
  max: 500.0
  mean: 245.3
  std: 32.1
  missing_rate: 0.008
  distribution: "近似正态 (Shapiro-Wilk p=0.23)"
  outlier_threshold_3sigma: [148.9, 341.7]
```

### 4. 异常传感器标注
- 基于 3σ 原则标注统计异常值
- 基于 IQR (四分位距) 标注离群值
- 输出异常汇总表：传感器名、异常样本数、异常比例

### 5. 输出产物
- `data/processed/secom_clean.parquet` — 清洗后数据
- `data/processed/secom_data_dict.yaml` — 数据字典
- `data/processed/secom_quality_report.md` — 质量报告
- 终端输出异常传感器排名 Top 10

## 半导体特定规则
- **保留层级关系**: Lot → Wafer → Die → Sensor，不做跨层级合并
- **时效性标记**: 如果数据含 Timestamp 列，检查时间跨度并标注数据漂移风险
- **单位敏感**: 压力 (mTorr/Torr/Pa)、温度 (C/K)、功率 (W/kW) 不可混淆
- **良率列保护**: 如果发现 `Yield` 或 `Label` 列，标记为 TARGET 且不做填充

## 使用方式
```
/dataset-curator --input data/sample/secom_sample.csv
/dataset-curator --input data/sample/ --output data/processed/
```
