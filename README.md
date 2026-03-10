# TaiPower Data 台灣電力公司即時發電數據

Real-time power generation data from [TaiPower](https://www.taipower.com.tw/) (台灣電力公司), collected every 5 minutes via GitHub Actions.

## Data Structure

```
data/
├── history.json          # Rolling 8-day raw records (5-min intervals)
└── dashboard.json        # Aggregated data for dashboard consumption
```

## Fields

| Field | Description |
|-------|-------------|
| `solar_mw` | Solar generation (MW) |
| `wind_mw` | Wind generation (MW) |
| `hydro_mw` | Hydro generation (MW) |
| `renewable_mw` | Total renewable generation (MW) |
| `total_mw` | Total generation (MW) |
| `renewable_pct` | Renewable share (%) |
| `coal_mw` | Coal generation (MW) |
| `lng_mw` | LNG generation (MW) |

## Usage

Dashboard JSON is consumed by [AI Sustainability Platform](https://github.com/ai-cooperation/ai-sustainability-platform):

```
https://raw.githubusercontent.com/ai-cooperation/taipower-data/main/data/dashboard.json
```

## Collection Schedule

- Every 5 minutes via GitHub Actions
- Rolling 8-day window (pruned automatically)
- ~2,300 records per 8-day cycle

## Source

- API: `https://www.taipower.com.tw/d006/loadGraph/loadGraph/data/genary.json`
- No authentication required
- Data updated every ~10 minutes by TaiPower
