import json
import re
import statistics
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / ".codex" / "config.toml"
OUTPUT = ROOT / "outputs" / "index.html"
TS_CODE = "601899.SH"
START_DATE = "20160613"
END_DATE = "20260702"


def get_token():
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([^\"&\s]+)", text)
    if not match:
        raise RuntimeError("Tushare token was not found.")
    return match.group(1)


def call_api(token, api_name, params, fields):
    payload = json.dumps(
        {"api_name": api_name, "token": token, "params": params, "fields": fields}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tushare.pro",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"{api_name}: {result.get('msg')}")
    data = result["data"]
    return [dict(zip(data["fields"], item)) for item in data["items"]]


def percentile(values, current):
    clean = [value for value in values if value is not None and value > 0]
    return round(sum(value <= current for value in clean) / len(clean) * 100, 1)


def median(values):
    clean = [float(value) for value in values if value is not None and value > 0]
    return round(statistics.median(clean), 3) if clean else None


def quarter_periods(start_year=2016, end_year=2026):
    periods = []
    for year in range(start_year, end_year + 1):
        for suffix in ("0331", "0630", "0930", "1231"):
            value = f"{year}{suffix}"
            if value <= END_DATE:
                periods.append(value)
    return periods


def build_data(token):
    daily = call_api(
        token,
        "daily_basic",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,close,turnover_rate,pe_ttm,pb,dv_ttm,total_mv,float_share",
    )
    quotes = call_api(
        token,
        "daily",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,close,vol,amount",
    )
    moneyflows = call_api(
        token,
        "moneyflow",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,buy_sm_amount,sell_sm_amount,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount",
    )
    margins = call_api(
        token,
        "margin_detail",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,rzye,rzmre,rzche",
    )
    holders = call_api(
        token,
        "stk_holdernumber",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "ann_date,end_date,holder_num",
    )
    hk_holds = call_api(
        token,
        "hk_hold",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,vol,ratio",
    )
    float_holders = call_api(
        token,
        "top10_floatholders",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "ann_date,end_date,holder_name,hold_amount,hold_ratio,hold_float_ratio,hold_change,holder_type",
    )
    top_holders = call_api(
        token,
        "top10_holders",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "ann_date,end_date,holder_name,hold_amount,hold_ratio,hold_change,holder_type",
    )
    holder_trades = call_api(
        token,
        "stk_holdertrade",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "ann_date,holder_name,holder_type,in_de,change_vol,change_ratio,after_share,after_ratio,avg_price,begin_date,close_date",
    )
    all_repurchase = call_api(
        token,
        "repurchase",
        {"start_date": START_DATE, "end_date": END_DATE},
        "ts_code,ann_date,end_date,proc,exp_date,vol,amount,high_limit,low_limit",
    )
    repurchases = [row for row in all_repurchase if row.get("ts_code") == TS_CODE]
    lpr_rows = call_api(
        token,
        "shibor_lpr",
        {"start_date": START_DATE, "end_date": END_DATE},
        "date,1y,5y",
    )
    fund_series = []
    for period in quarter_periods():
        rows = call_api(
            token,
            "fund_portfolio",
            {"period": period, "symbol": TS_CODE},
            "ann_date,end_date,ts_code,symbol,mkv,amount,stk_mkv_ratio,stk_float_ratio",
        )
        if not rows:
            continue
        latest_by_fund = {}
        for item in sorted(rows, key=lambda row: row.get("ann_date") or "", reverse=True):
            latest_by_fund.setdefault(item["ts_code"], item)
        values = list(latest_by_fund.values())
        fund_series.append(
            {
                "d": f"{period[:4]}-{period[4:6]}-{period[6:]}",
                "ann": max((row.get("ann_date") or period) for row in values),
                "count": len(values),
                "mkv": round(sum((row.get("mkv") or 0) for row in values) / 100000000, 2),
                "amount": round(sum((row.get("amount") or 0) for row in values) / 100000000, 3),
                "float_ratio": round(sum((row.get("stk_float_ratio") or 0) for row in values), 3),
            }
        )
    factors = call_api(
        token,
        "adj_factor",
        {"ts_code": TS_CODE, "start_date": START_DATE, "end_date": END_DATE},
        "trade_date,adj_factor",
    )
    reports = call_api(
        token,
        "report_rc",
        {"ts_code": TS_CODE, "start_date": "20260301", "end_date": END_DATE},
        "report_date,report_title,org_name,quarter,np,eps,pe,rating,min_price,max_price",
    )
    dividends = call_api(
        token,
        "dividend",
        {"ts_code": TS_CODE},
        "end_date,ann_date,div_proc,cash_div_tax,record_date,ex_date,pay_date",
    )
    forecasts = call_api(
        token,
        "forecast",
        {"ts_code": TS_CODE, "start_date": "20240101", "end_date": END_DATE},
        "ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,summary,change_reason",
    )

    factor_by_date = {row["trade_date"]: row["adj_factor"] for row in factors}
    quote_by_date = {row["trade_date"]: row for row in quotes}
    basic_by_date = {row["trade_date"]: row for row in daily}
    amount_by_date = {row["trade_date"]: row.get("amount") for row in quotes}
    moneyflow_by_date = {row["trade_date"]: row for row in moneyflows}
    margin_by_date = {row["trade_date"]: row for row in margins}
    latest_factor = factor_by_date[max(factor_by_date)]
    series = []
    for row in sorted(daily, key=lambda item: item["trade_date"]):
        pe = row.get("pe_ttm")
        pb = row.get("pb")
        market_cap = row.get("total_mv")
        factor = factor_by_date.get(row["trade_date"])
        amount = amount_by_date.get(row["trade_date"]) or 0
        moneyflow = moneyflow_by_date.get(row["trade_date"], {})
        margin = margin_by_date.get(row["trade_date"], {})
        if not pe or pe <= 0 or not pb or pb <= 0 or not market_cap or not factor:
            continue
        series.append(
            {
                "d": f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}",
                "p": round(row["close"] * factor / latest_factor, 3),
                "n": round(market_cap / pe / 10000, 2),
                "pe": round(pe, 3),
                "pb": round(pb, 3),
                "dy": round(row.get("dv_ttm") or 0, 3),
                "turn": round(row.get("turnover_rate") or 0, 3),
                "amount": round(amount / 100000, 3),
                "small": round(
                    ((moneyflow.get("buy_sm_amount") or 0) - (moneyflow.get("sell_sm_amount") or 0))
                    / 10000,
                    3,
                ),
                "large": round(
                    (
                        (moneyflow.get("buy_lg_amount") or 0)
                        + (moneyflow.get("buy_elg_amount") or 0)
                        - (moneyflow.get("sell_lg_amount") or 0)
                        - (moneyflow.get("sell_elg_amount") or 0)
                    )
                    / 10000,
                    3,
                ),
                "rzye": round((margin.get("rzye") or 0) / 100000000, 3),
                "rzbuy": round(
                    (margin.get("rzmre") or 0) / (amount * 1000) * 100, 3
                    if amount
                    else 0,
                ),
            }
        )
    last_basic_date = max(basic_by_date)
    for trade_date in sorted(date for date in quote_by_date if date > last_basic_date):
        quote = quote_by_date[trade_date]
        previous_basic = basic_by_date[last_basic_date]
        previous_series = series[-1]
        previous_close = previous_basic.get("close") or previous_series["p"]
        close = quote.get("close") or previous_close
        price_ratio = close / previous_close if previous_close else 1
        factor = factor_by_date.get(trade_date) or latest_factor
        amount = quote.get("amount") or 0
        moneyflow = moneyflow_by_date.get(trade_date, {})
        margin = margin_by_date.get(trade_date, {})
        float_share = previous_basic.get("float_share") or 0
        turnover_rate = (
            (quote.get("vol") or 0) / float_share
            if float_share and quote.get("vol")
            else previous_basic.get("turnover_rate") or previous_series["turn"]
        )
        pe = (previous_basic.get("pe_ttm") or previous_series["pe"]) * price_ratio
        pb = (previous_basic.get("pb") or previous_series["pb"]) * price_ratio
        dividend_yield = (previous_basic.get("dv_ttm") or previous_series["dy"]) / price_ratio
        market_cap = (previous_basic.get("total_mv") or 0) * price_ratio
        rzye = (
            round((margin.get("rzye") or 0) / 100000000, 3)
            if margin
            else previous_series["rzye"]
        )
        series.append(
            {
                "d": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}",
                "p": round(close * factor / latest_factor, 3),
                "n": round(market_cap / pe / 10000, 2) if pe else previous_series["n"],
                "pe": round(pe, 3),
                "pb": round(pb, 3),
                "dy": round(dividend_yield, 3),
                "turn": round(turnover_rate or 0, 3),
                "amount": round(amount / 100000, 3),
                "small": round(
                    ((moneyflow.get("buy_sm_amount") or 0) - (moneyflow.get("sell_sm_amount") or 0))
                    / 10000,
                    3,
                ),
                "large": round(
                    (
                        (moneyflow.get("buy_lg_amount") or 0)
                        + (moneyflow.get("buy_elg_amount") or 0)
                        - (moneyflow.get("sell_lg_amount") or 0)
                        - (moneyflow.get("sell_elg_amount") or 0)
                    )
                    / 10000,
                    3,
                ),
                "rzye": rzye,
                "rzbuy": round(
                    (margin.get("rzmre") or 0) / (amount * 1000) * 100
                    if margin and amount
                    else 0,
                    3,
                ),
            }
        )
    latest = series[-1]
    latest.update(
        {
            "pe_pct": percentile([row["pe"] for row in series], latest["pe"]),
            "pb_pct": percentile([row["pb"] for row in series], latest["pb"]),
            "dy_pct": percentile([row["dy"] for row in series], latest["dy"]),
        }
    )

    latest_by_org_year = {}
    for row in sorted(reports, key=lambda item: item["report_date"], reverse=True):
        year = str(row.get("quarter", ""))[:4]
        key = (row.get("org_name"), year)
        if year in {"2026", "2027", "2028"} and row.get("eps") and key not in latest_by_org_year:
            latest_by_org_year[key] = row

    consensus = {}
    for year in ("2026", "2027", "2028"):
        rows = [row for (org, y), row in latest_by_org_year.items() if y == year]
        eps_values = [row["eps"] for row in rows]
        np_values = [row["np"] / 10000 for row in rows if row.get("np")]
        eps_mid = median(eps_values)
        consensus[year] = {
            "eps": eps_mid,
            "np": median(np_values),
            "forward_pe": round(latest["p"] / eps_mid, 2) if eps_mid else None,
            "count": len(rows),
            "eps_low": round(min(eps_values), 2) if eps_values else None,
            "eps_high": round(max(eps_values), 2) if eps_values else None,
        }

    target_latest = {}
    for row in sorted(reports, key=lambda item: item["report_date"], reverse=True):
        target = row.get("min_price") or row.get("max_price")
        org = row.get("org_name")
        if target and org not in target_latest:
            target_latest[org] = float(target)
    target_values = list(target_latest.values())

    recent_reports = []
    seen_titles = set()
    for row in sorted(reports, key=lambda item: item["report_date"], reverse=True):
        title = row.get("report_title")
        if title and "紫金矿业" in title and title not in seen_titles:
            seen_titles.add(title)
            recent_reports.append(
                {
                    "date": row["report_date"],
                    "org": row.get("org_name") or "",
                    "title": title,
                    "rating": row.get("rating") or "",
                }
            )
        if len(recent_reports) == 6:
            break

    dividend_events = []
    used_dividends = set()
    for row in sorted(dividends, key=lambda item: item.get("ann_date") or "", reverse=True):
        if not row.get("end_date"):
            continue
        key = (row["end_date"], row.get("cash_div_tax"))
        if key in used_dividends:
            continue
        used_dividends.add(key)
        event_date = row.get("ann_date") or row["end_date"]
        dividend_events.append(
            {
                "date": event_date,
                "text": f"{row['end_date'][:4]}年分红方案：每股现金 {row.get('cash_div_tax') or 0:.2f} 元（{row.get('div_proc') or '待定'}）",
            }
        )

    forecast_events = []
    used_forecasts = set()
    for row in sorted(forecasts, key=lambda item: item.get("ann_date") or "", reverse=True):
        if not row.get("end_date") or row["end_date"] in used_forecasts:
            continue
        used_forecasts.add(row["end_date"])
        event_date = row.get("ann_date") or row["end_date"]
        low = (row.get("net_profit_min") or 0) / 10000
        high = (row.get("net_profit_max") or low * 10000) / 10000
        forecast_events.append(
            {
                "date": event_date,
                "text": f"{row['end_date'][:4]}年业绩{row.get('type') or '预告'}：归母净利润约 {low:.0f}–{high:.0f} 亿元",
            }
        )

    holder_series = []
    seen_holder_dates = set()
    for row in sorted(holders, key=lambda item: item["end_date"]):
        if row["end_date"] in seen_holder_dates:
            continue
        seen_holder_dates.add(row["end_date"])
        holder_series.append(
            {
                "d": f"{row['end_date'][:4]}-{row['end_date'][4:6]}-{row['end_date'][6:]}",
                "ann": row["ann_date"],
                "v": row["holder_num"],
            }
        )

    sentiment_events = []
    for index, latest_holder in enumerate(holder_series):
        previous_holder = holder_series[index - 1] if index else None
        change = (
            (latest_holder["v"] / previous_holder["v"] - 1) * 100
            if previous_holder and previous_holder["v"]
            else 0
        )
        sentiment_events.append(
            {
                "date": latest_holder["ann"],
                "text": f"股东户数 {latest_holder['v'] / 10000:.1f} 万户"
                + (
                    f"，较上期 {'增加' if change >= 0 else '减少'} {abs(change):.1f}%"
                    if previous_holder
                    else ""
                ),
            }
        )

    hk_series = []
    seen_hk_dates = set()
    for row in sorted(hk_holds, key=lambda item: item["trade_date"]):
        if row["trade_date"] in seen_hk_dates:
            continue
        seen_hk_dates.add(row["trade_date"])
        hk_series.append(
            {
                "d": f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}",
                "vol": row.get("vol") or 0,
                "ratio": row.get("ratio") or 0,
            }
        )

    grouped_institutions = {}
    institutional_names = {}
    for row in float_holders:
        period = row["end_date"]
        if row.get("holder_type") == "个人" or row.get("hold_float_ratio") is None:
            continue
        grouped_institutions.setdefault(period, []).append(row)
        institutional_names.setdefault(period, set()).add(row["holder_name"])
    institution_series = []
    for period, rows in sorted(grouped_institutions.items()):
        institution_series.append(
            {
                "d": f"{period[:4]}-{period[4:6]}-{period[6:]}",
                "ratio": round(sum(row["hold_float_ratio"] for row in rows), 3),
                "count": len(rows),
            }
        )

    big_events = []
    quarter_hk = {}
    for row in hk_series:
        quarter = (int(row["d"][5:7]) - 1) // 3 + 1
        quarter_hk[(row["d"][:4], quarter)] = row
    quarter_hk_values = list(quarter_hk.values())
    for index, current in enumerate(quarter_hk_values):
        if not index:
            continue
        previous = quarter_hk_values[index - 1]
        delta = current["ratio"] - previous["ratio"]
        big_events.append(
            {
                "date": current["d"].replace("-", ""),
                "text": f"沪股通持股比例 {current['ratio']:.2f}%，较上期 {'增加' if delta >= 0 else '减少'} {abs(delta):.2f} 个百分点",
            }
        )
    for current in fund_series:
        comparable = next(
            (
                row
                for row in reversed(fund_series)
                if row["d"] < current["d"]
                if row["d"][5:] == current["d"][5:]
            ),
            None,
        )
        if comparable:
            count_change = current["count"] - comparable["count"]
            big_events.append(
                {
                    "date": current["ann"],
                    "text": f"公募披露持仓基金 {current['count']} 只，同比 {'增加' if count_change >= 0 else '减少'} {abs(count_change)} 只；合计持仓市值 {current['mkv']:.1f} 亿元",
                }
            )
    periods = sorted(institutional_names)
    for index, current_period in enumerate(periods):
        if not index:
            continue
        previous_period = periods[index - 1]
        entrants = institutional_names[current_period] - institutional_names[previous_period]
        exits = institutional_names[previous_period] - institutional_names[current_period]
        if entrants:
            big_events.append(
                {
                    "date": current_period,
                    "text": "新进入前十大流通股东：" + "、".join(sorted(entrants)[:3]),
                }
            )
        if exits:
            big_events.append(
                {
                    "date": current_period,
                    "text": "退出前十大流通股东：" + "、".join(sorted(exits)[:3]),
                }
            )

    official_names = ("中央汇金", "中国证券金融", "全国社保基金", "社会保障基金", "社保基金")
    official_grouped = {}
    for row in top_holders:
        if any(name in row["holder_name"] for name in official_names):
            official_grouped.setdefault(row["end_date"], []).append(row)
    official_hold_series = []
    for period, rows in sorted(official_grouped.items()):
        official_hold_series.append(
            {
                "d": f"{period[:4]}-{period[4:6]}-{period[6:]}",
                "ratio": round(sum((row.get("hold_ratio") or 0) for row in rows), 3),
                "amount": round(sum((row.get("hold_amount") or 0) for row in rows) / 100000000, 3),
                "count": len(rows),
                "names": [row["holder_name"] for row in rows],
            }
        )

    repurchase_series = []
    seen_repurchase = set()
    for row in sorted(repurchases, key=lambda item: item.get("ann_date") or ""):
        if not row.get("ann_date"):
            continue
        key = (row["ann_date"], row.get("proc"), row.get("amount"))
        if key in seen_repurchase:
            continue
        seen_repurchase.add(key)
        repurchase_series.append(
            {
                "d": f"{row['ann_date'][:4]}-{row['ann_date'][4:6]}-{row['ann_date'][6:]}",
                "amount": round((row.get("amount") or 0) / 100000000, 3),
                "vol": round((row.get("vol") or 0) / 100000000, 3),
                "proc": row.get("proc") or "",
            }
        )

    holder_trade_series = []
    cumulative_trade = 0
    for row in sorted(holder_trades, key=lambda item: item.get("ann_date") or ""):
        if not row.get("ann_date"):
            continue
        signed_ratio = (row.get("change_ratio") or 0) * (1 if row.get("in_de") == "IN" else -1)
        cumulative_trade += signed_ratio
        holder_trade_series.append(
            {
                "d": f"{row['ann_date'][:4]}-{row['ann_date'][4:6]}-{row['ann_date'][6:]}",
                "ratio": round(cumulative_trade, 4),
                "change": round(signed_ratio, 4),
                "holder": row.get("holder_name") or "",
                "price": row.get("avg_price"),
                "type": row.get("in_de") or "",
            }
        )

    lpr_series = []
    seen_lpr = set()
    for row in sorted(lpr_rows, key=lambda item: item["date"]):
        if row.get("1y") is None or row.get("5y") is None:
            continue
        key = (row["date"], row.get("1y"), row.get("5y"))
        if key in seen_lpr:
            continue
        seen_lpr.add(key)
        lpr_series.append(
            {
                "d": f"{row['date'][:4]}-{row['date'][4:6]}-{row['date'][6:]}",
                "y1": row.get("1y"),
                "y5": row.get("5y"),
            }
        )

    official_events = []
    for row in repurchase_series:
        official_events.append(
            {
                "date": row["d"].replace("-", ""),
                "text": f"股份回购{row['proc']}：金额 {row['amount']:.2f} 亿元"
                + (f"，数量 {row['vol']:.2f} 亿股" if row["vol"] else ""),
            }
        )
    for row in holder_trades:
        action = "增持" if row.get("in_de") == "IN" else "减持"
        official_events.append(
            {
                "date": row["ann_date"],
                "text": f"{row.get('holder_name') or '重要股东'}{action} {abs(row.get('change_ratio') or 0):.2f}%"
                + (f"，均价 {row['avg_price']:.2f} 元" if row.get("avg_price") else ""),
            }
        )
    for index, row in enumerate(official_hold_series):
        previous = official_hold_series[index - 1] if index else None
        delta = row["ratio"] - previous["ratio"] if previous else 0
        official_events.append(
            {
                "date": row["d"].replace("-", ""),
                "text": f"国家队/社保持股比例 {row['ratio']:.2f}%"
                + (f"，较上期 {'增加' if delta >= 0 else '减少'} {abs(delta):.2f} 个百分点" if previous else ""),
            }
        )
    for index, row in enumerate(lpr_series):
        previous = lpr_series[index - 1] if index else None
        if previous and (row["y1"] != previous["y1"] or row["y5"] != previous["y5"]):
            official_events.append(
                {
                    "date": row["d"].replace("-", ""),
                    "text": f"LPR调整：1年期 {row['y1']:.2f}%，5年期 {row['y5']:.2f}%",
                }
            )

    valid_margin = [row for row in series if row["rzye"] > 0]
    quarter_margin = {}
    for index, row in enumerate(valid_margin):
        quarter = (int(row["d"][5:7]) - 1) // 3 + 1
        quarter_margin[(row["d"][:4], quarter)] = (index, row)
    for position, latest_margin in quarter_margin.values():
        prior_year = valid_margin[max(0, position - 252) : position]
        high_note = (
            "，创近一年新高"
            if prior_year and latest_margin["rzye"] >= max(row["rzye"] for row in prior_year)
            else ""
        )
        sentiment_events.append(
            {
                "date": latest_margin["d"].replace("-", ""),
                "text": f"季度末融资余额 {latest_margin['rzye']:.1f} 亿元，融资买入占比 {latest_margin['rzbuy']:.1f}%{high_note}",
            }
        )

    quarter_last_indices = {}
    for index, row in enumerate(series):
        quarter = (int(row["d"][5:7]) - 1) // 3 + 1
        quarter_last_indices[(row["d"][:4], quarter)] = index
    for index in quarter_last_indices.values():
        if index < 39:
            continue
        latest_row = series[index]
        amount20 = statistics.mean(row["amount"] for row in series[index - 19 : index + 1])
        amount_prev = statistics.mean(row["amount"] for row in series[index - 39 : index - 19])
        turn20 = statistics.mean(row["turn"] for row in series[index - 19 : index + 1])
        heat_change = (amount20 / amount_prev - 1) * 100 if amount_prev else 0
        sentiment_events.append(
            {
                "date": latest_row["d"].replace("-", ""),
                "text": f"近20日平均成交额 {amount20:.1f} 亿元，较此前20日 {'上升' if heat_change >= 0 else '下降'} {abs(heat_change):.1f}%；平均换手率 {turn20:.2f}%",
            }
        )

    return {
        "series": series,
        "latest": latest,
        "consensus": consensus,
        "target": {
            "median": median(target_values),
            "low": round(min(target_values), 2) if target_values else None,
            "high": round(max(target_values), 2) if target_values else None,
            "count": len(target_values),
        },
        "reports": recent_reports,
        "events": sorted(dividend_events + forecast_events, key=lambda item: item["date"], reverse=True),
        "holders": holder_series,
        "sentiment_events": sorted(sentiment_events, key=lambda item: item["date"], reverse=True),
        "hk_holds": hk_series,
        "funds": fund_series,
        "institutions": institution_series,
        "big_events": sorted(big_events, key=lambda item: item["date"], reverse=True),
        "official_holds": official_hold_series,
        "repurchases": repurchase_series,
        "holder_trades": holder_trade_series,
        "lpr": lpr_series,
        "official_events": sorted(official_events, key=lambda item: item["date"], reverse=True),
    }


HTML = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>紫金矿业研究面板</title>
<style>
:root{--bg:#071019;--panel:#0b1723;--line:#203141;--text:#eaf2f8;--muted:#8294a6;--cyan:#42d3ff;--gold:#ffb547;--purple:#c792ff;--green:#40df9a;--red:#ff6b7d}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#11283a 0,transparent 36%),var(--bg);color:var(--text);font-family:Inter,"Microsoft YaHei",system-ui,sans-serif}
.wrap{width:100%;max-width:1500px;margin:auto;padding:24px;overflow:hidden}.header{display:flex;justify-content:space-between;gap:16px;align-items:flex-end}.header h1{font-size:27px;margin:0 0 6px}.muted{color:var(--muted)}.badge{border:1px solid #284052;border-radius:999px;padding:8px 12px;color:#a8bac8;font-size:12px;white-space:nowrap}
.nav{display:flex;gap:6px;margin:20px 0 14px;border-bottom:1px solid #193040}.nav button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;padding:10px 18px}.nav button.active{color:#fff;border-color:var(--cyan)}
button{background:#101f2c;color:#9eb0be;border:1px solid #243847;border-radius:8px;padding:7px 11px;cursor:pointer}button:hover,button.active{color:#fff;border-color:#3b6077;background:#173044}
.page{display:block;min-width:0;scroll-margin-top:12px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}.card,.panel{min-width:0;background:linear-gradient(145deg,#0e1d2a,#09131e);border:1px solid #1b2c3a;border-radius:14px;padding:15px}
.label{color:var(--muted);font-size:12px}.value{font-size:23px;font-weight:750;margin-top:5px}.hint{font-size:11px;color:#667d8f;margin-top:5px}.cyan{color:var(--cyan)}.gold{color:var(--gold)}.purple{color:var(--purple)}.green{color:var(--green)}
.panel{margin-bottom:14px}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.group{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.chart-wrap{height:570px;position:relative;margin-top:10px}.small-chart{height:430px}canvas{width:100%;height:100%;display:block}
.module-head{padding:14px 0 18px}.eyebrow{color:#ffc84a;font-weight:800;font-size:12px;letter-spacing:1.5px}.module-head h2{font-size:30px;margin:7px 0 5px}.valuation-panel{padding:0;overflow:hidden}.valuation-panel-head{padding:16px;border-bottom:1px solid #1c3243}.valuation-panel-body{padding:14px 16px 16px}.metric-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.metric-tabs button.active{background:#ffc84a;border-color:#ffc84a;color:#071019;font-weight:800}.metric-note{display:flex;justify-content:space-between;gap:14px;color:#86a0b5;font-size:12px;line-height:1.5}.metric-current{color:#eaf2f8;font-weight:700;white-space:nowrap}.valuation-main-chart{height:470px}.navigator{height:42px;margin:0 52px 2px;position:relative;border:1px solid #31495b;border-radius:4px;background:#101c27;overflow:hidden}.navigator canvas{opacity:.8}.navigator-window{position:absolute;top:0;bottom:0;right:0;border:1px solid #ffc84a;background:#ffc84a12;pointer-events:none}
.tip{position:absolute;display:none;pointer-events:none;background:#071019f2;border:1px solid #345064;border-radius:10px;padding:9px 11px;font-size:12px;line-height:1.65;box-shadow:0 8px 30px #0009;min-width:175px}
.toggle{display:flex;align-items:center;gap:5px;font-size:12px}.dot{width:9px;height:9px;border-radius:50%}.section-title{font-size:17px;margin:0}.grid2{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:14px}.forecast-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}
.forecast{border:1px solid #1d3545;border-radius:11px;padding:13px;background:#091522}.forecast strong{font-size:19px}.bar{height:8px;background:#142837;border-radius:8px;margin:9px 0 5px;overflow:hidden}.bar span{height:100%;display:block;background:linear-gradient(90deg,var(--cyan),var(--purple))}
.events{display:grid;gap:8px;margin-top:12px}.event{border-left:2px solid #35576c;padding:4px 0 4px 11px;font-size:13px;line-height:1.5}.date{color:#7290a5;font-size:11px}
.event-head{display:flex;justify-content:space-between;align-items:center;gap:14px}.event-head .hint{margin-top:4px}.event-filters{display:flex;gap:8px}.event-filters select{appearance:none;background:#102035;color:#eaf2f8;border:1px solid #345064;border-radius:8px;padding:8px 30px 8px 11px;font:inherit;background-image:linear-gradient(45deg,transparent 50%,#9eb4c4 50%),linear-gradient(135deg,#9eb4c4 50%,transparent 50%);background-position:calc(100% - 14px) 13px,calc(100% - 9px) 13px;background-size:5px 5px,5px 5px;background-repeat:no-repeat}.empty-event{color:#718596;padding:18px 4px}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:12px}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #193040;vertical-align:top}th{color:#7890a3;font-weight:600}
.foot{color:#6f8495;font-size:11px;line-height:1.6;padding:4px}.pill{display:inline-block;border:1px solid #2b4658;border-radius:999px;padding:2px 7px;color:#9eb4c4}
@media(max-width:1200px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:1fr}.forecast-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:850px){.wrap{padding:13px}.header{align-items:flex-start;flex-direction:column}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:1fr}.forecast-grid{grid-template-columns:1fr}.chart-wrap{height:500px}.small-chart{height:390px}.valuation-main-chart{height:430px}.metric-note,.event-head{flex-direction:column;align-items:flex-start}.event-filters{width:100%}.event-filters select{flex:1}.metric-current{white-space:normal}.navigator{margin:0 18px}.nav{overflow:auto}.nav button{white-space:nowrap}}
</style></head><body><main class="wrap">
<header class="header"><div><h1>紫金矿业 <span class="muted" style="font-weight:500">601899.SH</span></h1><div class="muted">价格、盈利、估值与预期的连续跟踪面板</div></div><div class="badge">数据截至 2026-06-12</div></header>
<nav class="nav"><button class="active" data-page="overview">总览</button><button data-page="valuation">估值</button><button data-page="retail">情绪·散户</button><button data-page="bigmoney">情绪·大资金</button><button data-page="official">情绪·官方</button></nav>

<section id="overview" class="page active">
<div class="cards">
 <div class="card"><div class="label">前复权收盘价</div><div id="lastPrice" class="value cyan"></div></div>
 <div class="card"><div class="label">滚动12个月归母净利润</div><div id="lastProfit" class="value gold"></div></div>
 <div class="card"><div class="label">市盈率 PE(TTM)</div><div id="lastPe" class="value purple"></div></div>
 <div class="card"><div class="label">十年股价变化</div><div id="return10y" class="value"></div></div>
</div>
<div class="panel"><div class="toolbar"><div class="group" id="overviewRanges"><button data-y="1">近1年</button><button data-y="3">近3年</button><button data-y="5">近5年</button><button data-y="10" class="active">近10年</button></div>
<div class="group"><label class="toggle"><input type="checkbox" data-overview="p" checked><span class="dot" style="background:var(--cyan)"></span>股价</label><label class="toggle"><input type="checkbox" data-overview="n" checked><span class="dot" style="background:var(--gold)"></span>滚动利润</label><label class="toggle"><input type="checkbox" data-overview="pe" checked><span class="dot" style="background:var(--purple)"></span>PE(TTM)</label></div></div>
<div class="chart-wrap"><canvas id="overviewChart"></canvas><div id="overviewTip" class="tip"></div></div></div>
</section>

<section id="valuation" class="page">
<div class="module-head"><div class="eyebrow">MODULE 01 / VALUATION</div><h2>估值</h2><div class="muted">连续数据看估值位置，并结合盈利周期理解市场为紫金矿业支付的价格。</div></div>
<div class="panel valuation-panel">
 <div class="valuation-panel-head"><div class="toolbar"><div><h2 id="valuationChartTitle" class="section-title">PE(TTM) 长期走势</h2><div class="hint">横轴为交易日期，按日连续展示</div></div><div class="group" id="valuationRanges"><button data-y="3">3年</button><button data-y="5">5年</button><button data-y="10" class="active">10年</button><button data-y="0">全部</button></div></div></div>
 <div class="valuation-panel-body">
  <div class="metric-tabs" id="metricButtons"><button data-metric="pe" class="active">PE(TTM)</button><button data-metric="pb">PB</button><button data-metric="dy">股息收益率</button><button data-metric="pe_pct">PE历史分位</button><button data-metric="pb_pct">PB历史分位</button></div>
  <div class="metric-note"><span id="metricDescription">PE越高，市场对未来盈利增长的要求越高。</span><span id="metricCurrent" class="metric-current"></span></div>
  <div class="chart-wrap valuation-main-chart"><canvas id="valuationChart"></canvas><div id="valuationTip" class="tip"></div></div>
  <div class="navigator"><canvas id="valuationNavigator"></canvas><div id="navigatorWindow" class="navigator-window"></div></div>
 </div>
</div>
<div class="cards">
 <div class="card"><div class="label">PE(TTM)</div><div id="vPe" class="value purple"></div><div id="vPePct" class="hint"></div></div>
 <div class="card"><div class="label">PB</div><div id="vPb" class="value cyan"></div><div id="vPbPct" class="hint"></div></div>
 <div class="card"><div class="label">股息率 TTM</div><div id="vDy" class="value green"></div><div id="vDyPct" class="hint"></div></div>
 <div class="card"><div class="label">机构目标价中位数</div><div id="targetPrice" class="value gold"></div><div id="targetHint" class="hint"></div></div>
</div>
<div class="grid2">
 <div class="panel"><h2 class="section-title">未来三年机构盈利共识</h2><div id="forecastGrid" class="forecast-grid"></div><div class="foot">口径：2026-03-01 以来，每家机构仅保留最新预测，再取 EPS 中位数；远期 PE = 最新股价 ÷ EPS 中位数。</div></div>
 <div class="panel"><div class="event-head"><div><h2 class="section-title">估值事件 List</h2><div class="hint">按年份和季度切换：业绩预告与分红事件</div></div><div class="event-filters"><select id="valuationEventYear" aria-label="估值事件年份"></select><select id="valuationEventQuarter" aria-label="估值事件季度"></select></div></div><div id="events" class="events"></div></div>
</div>
<div class="panel"><h2 class="section-title">近期机构观点</h2><table><thead><tr><th>日期</th><th>机构</th><th>标题</th><th>评级</th></tr></thead><tbody id="reports"></tbody></table></div>
</section>

<section id="retail" class="page">
<div class="module-head"><div class="eyebrow">MODULE 02 / RETAIL SENTIMENT</div><h2>情绪·散户</h2><div class="muted">用交易活跃度、小单资金、融资盘和股东户数，连续观察散户情绪与拥挤度。</div></div>
<div class="panel valuation-panel">
 <div class="valuation-panel-head"><div class="toolbar"><div><h2 id="retailChartTitle" class="section-title">换手率长期走势</h2><div class="hint">横轴为交易日期；股东户数按公司实际披露节点展示</div></div><div class="group" id="retailRanges"><button data-y="1">1年</button><button data-y="3" class="active">3年</button><button data-y="5">5年</button><button data-y="10">10年</button></div></div></div>
 <div class="valuation-panel-body">
  <div class="metric-tabs" id="retailMetricButtons"><button data-metric="turn" class="active">换手率</button><button data-metric="amount">成交额</button><button data-metric="small">小单净流入</button><button data-metric="rzye">融资余额</button><button data-metric="rzbuy">融资买入占比</button><button data-metric="holders">股东户数</button></div>
  <div class="metric-note"><span id="retailDescription">换手率反映筹码交换和市场参与热度。</span><span id="retailCurrent" class="metric-current"></span></div>
  <div class="chart-wrap valuation-main-chart"><canvas id="retailChart"></canvas><div id="retailTip" class="tip"></div></div>
 </div>
</div>
<div class="cards">
 <div class="card"><div class="label">最新换手率</div><div id="rTurn" class="value cyan"></div><div id="rTurnHint" class="hint"></div></div>
 <div class="card"><div class="label">当日成交额</div><div id="rAmount" class="value gold"></div><div id="rAmountHint" class="hint"></div></div>
 <div class="card"><div class="label">小单净流入</div><div id="rSmall" class="value green"></div><div class="hint">正值为小单净流入</div></div>
 <div class="card"><div class="label">融资余额</div><div id="rMargin" class="value purple"></div><div id="rMarginHint" class="hint"></div></div>
 <div class="card"><div class="label">融资买入占比</div><div id="rMarginBuy" class="value cyan"></div><div class="hint">融资买入额 ÷ 当日成交额</div></div>
 <div class="card"><div class="label">最新披露股东户数</div><div id="rHolders" class="value gold"></div><div id="rHolderHint" class="hint"></div></div>
</div>
<div class="panel"><div class="event-head"><div><h2 class="section-title">散户情绪事件 List</h2><div class="hint">按年份和季度切换：融资盘、市场热度与股东户数</div></div><div class="event-filters"><select id="retailEventYear" aria-label="散户事件年份"></select><select id="retailEventQuarter" aria-label="散户事件季度"></select></div></div><div id="sentimentEvents" class="events"></div></div>
</section>

<section id="bigmoney" class="page">
<div class="module-head"><div class="eyebrow">MODULE 03 / INSTITUTIONAL FLOWS</div><h2>情绪·大资金</h2><div class="muted">跟踪大额成交、沪股通、公募基金与主要机构持仓的连续变化。</div></div>
<div class="panel valuation-panel">
 <div class="valuation-panel-head"><div class="toolbar"><div><h2 id="bigChartTitle" class="section-title">大单及超大单净额长期走势</h2><div class="hint">日度资金流与季度持仓数据按各自真实披露频率展示</div></div><div class="group" id="bigRanges"><button data-y="1">1年</button><button data-y="3" class="active">3年</button><button data-y="5">5年</button><button data-y="10">10年</button></div></div></div>
 <div class="valuation-panel-body">
  <div class="metric-tabs" id="bigMetricButtons"><button data-metric="large" class="active">大单及超大单净额</button><button data-metric="hk">沪股通持股比例</button><button data-metric="fund_count">基金数量</button><button data-metric="fund_mkv">基金持仓市值</button><button data-metric="fund_ratio">基金流通占比</button><button data-metric="institution">机构持股比例</button></div>
  <div class="metric-note"><span id="bigDescription">大单及超大单净额反映大额交易资金的当日方向。</span><span id="bigCurrent" class="metric-current"></span></div>
  <div class="chart-wrap valuation-main-chart"><canvas id="bigChart"></canvas><div id="bigTip" class="tip"></div></div>
 </div>
</div>
<div class="cards">
 <div class="card"><div class="label">大单及超大单净额</div><div id="bLarge" class="value cyan"></div><div class="hint">正值为净流入</div></div>
 <div class="card"><div class="label">沪股通持股比例</div><div id="bHk" class="value gold"></div><div id="bHkHint" class="hint"></div></div>
 <div class="card"><div class="label">披露持仓基金数量</div><div id="bFundCount" class="value purple"></div><div id="bFundCountHint" class="hint"></div></div>
 <div class="card"><div class="label">公募持仓市值</div><div id="bFundMkv" class="value green"></div><div id="bFundMkvHint" class="hint"></div></div>
 <div class="card"><div class="label">基金流通占比</div><div id="bFundRatio" class="value cyan"></div><div class="hint">各基金持股占流通股比例合计</div></div>
 <div class="card"><div class="label">前十大机构流通占比</div><div id="bInstitution" class="value gold"></div><div id="bInstitutionHint" class="hint"></div></div>
</div>
<div class="panel"><div class="event-head"><div><h2 class="section-title">大资金事件 List</h2><div class="hint">按年份和季度切换：沪股通、公募与前十大机构变化</div></div><div class="event-filters"><select id="bigEventYear" aria-label="大资金事件年份"></select><select id="bigEventQuarter" aria-label="大资金事件季度"></select></div></div><div id="bigEvents" class="events"></div></div>
</section>

<section id="official" class="page">
<div class="module-head"><div class="eyebrow">MODULE 04 / OFFICIAL SIGNALS</div><h2>情绪·官方</h2><div class="muted">跟踪公司正式资本动作、重要股东、国家队持仓及货币政策利率环境。</div></div>
<div class="panel valuation-panel">
 <div class="valuation-panel-head"><div class="toolbar"><div><h2 id="officialChartTitle" class="section-title">国家队/社保持股比例长期走势</h2><div class="hint">公司行为按公告节点，持仓按财报期，LPR按公布日期展示</div></div><div class="group" id="officialRanges"><button data-y="3">3年</button><button data-y="5">5年</button><button data-y="10" class="active">10年</button></div></div></div>
 <div class="valuation-panel-body">
  <div class="metric-tabs" id="officialMetricButtons"><button data-metric="official_hold" class="active">国家队/社保持股</button><button data-metric="repurchase">累计回购金额</button><button data-metric="holder_trade">重要股东累计增减持</button><button data-metric="lpr1">1年期LPR</button><button data-metric="lpr5">5年期LPR</button></div>
  <div class="metric-note"><span id="officialDescription">统计前十大股东中的中国证券金融、中央汇金和社保基金持仓。</span><span id="officialCurrent" class="metric-current"></span></div>
  <div class="chart-wrap valuation-main-chart"><canvas id="officialChart"></canvas><div id="officialTip" class="tip"></div></div>
 </div>
</div>
<div class="cards">
 <div class="card"><div class="label">最新回购状态</div><div id="oRepurchase" class="value gold"></div><div id="oRepurchaseHint" class="hint"></div></div>
 <div class="card"><div class="label">重要股东累计增减持</div><div id="oHolderTrade" class="value cyan"></div><div id="oHolderTradeHint" class="hint"></div></div>
 <div class="card"><div class="label">国家队/社保持股比例</div><div id="oOfficialHold" class="value purple"></div><div id="oOfficialHoldHint" class="hint"></div></div>
 <div class="card"><div class="label">1年期 / 5年期 LPR</div><div id="oLpr" class="value green"></div><div id="oLprHint" class="hint"></div></div>
 <div class="card"><div class="label">近十年增发融资</div><div class="value muted">未发现记录</div><div class="hint">未发现可核验的A股增发融资明细</div></div>
 <div class="card"><div class="label">官方数据口径</div><div class="value" style="font-size:16px">公告与正式披露</div><div class="hint">不使用传闻或无法核验的政策新闻</div></div>
</div>
<div class="panel"><div class="event-head"><div><h2 class="section-title">官方事件 List</h2><div class="hint">按年份和季度切换：回购、增减持、国家队持仓与LPR调整</div></div><div class="event-filters"><select id="officialEventYear" aria-label="官方事件年份"></select><select id="officialEventQuarter" aria-label="官方事件季度"></select></div></div><div id="officialEvents" class="events"></div></div>
</section>
<div class="foot">数据源：Tushare。机构盈利预测是统计汇总，不代表公司指引或投资建议；历史分位受盈利周期和会计口径变化影响。</div>
</main><script>
const MODEL=__MODEL__;
const DATA=MODEL.series,L=MODEL.latest,COLORS={p:'#42d3ff',n:'#ffb547',pe:'#c792ff',pb:'#42d3ff',dy:'#40df9a'};
function setActiveNav(name){document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===name))}
function goToSection(name,behavior='smooth'){const target=document.getElementById(name)||overview;setActiveNav(target.id);target.scrollIntoView({behavior,block:'start'});setTimeout(()=>{drawOverview();drawValuation();drawRetail();drawBig();drawOfficial()},50)}
document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>{history.replaceState(null,'','#'+b.dataset.page);goToSection(b.dataset.page)});
window.addEventListener('load',()=>{const target=location.hash.slice(1);if(['valuation','retail','bigmoney','official'].includes(target))goToSection(target,'auto');else setActiveNav('overview')});
function syncNavToScroll(){const marker=scrollY+innerHeight*.28;setActiveNav(marker>=official.offsetTop?'official':marker>=bigmoney.offsetTop?'bigmoney':marker>=retail.offsetTop?'retail':marker>=valuation.offsetTop?'valuation':'overview')}
addEventListener('scroll',syncNavToScroll,{passive:true});
lastPrice.textContent=L.p.toFixed(2)+' 元';lastProfit.textContent=L.n.toFixed(2)+' 亿元';lastPe.textContent=L.pe.toFixed(2)+' 倍';
const ret=(L.p/DATA[0].p-1)*100;return10y.textContent=(ret>=0?'+':'')+ret.toFixed(1)+'%';return10y.style.color=ret>=0?'var(--green)':'var(--red)';
vPe.textContent=L.pe.toFixed(2)+' 倍';vPePct.textContent='十年 '+L.pe_pct+'% 分位';
vPb.textContent=L.pb.toFixed(2)+' 倍';vPbPct.textContent='十年 '+L.pb_pct+'% 分位';
vDy.textContent=L.dy.toFixed(2)+'%';vDyPct.textContent='十年 '+L.dy_pct+'% 分位';
targetPrice.textContent=MODEL.target.median?MODEL.target.median.toFixed(2)+' 元':'暂无';targetHint.textContent=MODEL.target.count?MODEL.target.count+' 家机构，区间 '+MODEL.target.low+'–'+MODEL.target.high+' 元':'近期无目标价样本';
function setupCanvas(canvas){const dpr=devicePixelRatio||1,r=canvas.getBoundingClientRect(),ctx=canvas.getContext('2d');canvas.width=r.width*dpr;canvas.height=r.height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);return {ctx,w:r.width,h:r.height}}
function ext(values,pad=.1){const a=values.filter(Number.isFinite),mn=Math.min(...a),mx=Math.max(...a),p=(mx-mn||1)*pad;return [Math.max(0,mn-p),mx+p]}
let oy=10,ov={p:true,n:true,pe:true},overviewView=[];
function drawOverview(){const canvas=overviewChart;if(!canvas.offsetWidth)return;const end=new Date(DATA.at(-1).d),start=new Date(end);start.setFullYear(end.getFullYear()-oy);overviewView=DATA.filter(d=>new Date(d.d)>=start);const {ctx,w,h}=setupCanvas(canvas),m={l:62,r:112,t:25,b:42},cw=w-m.l-m.r,ch=h-m.t-m.b,ex={p:ext(overviewView.map(d=>d.p)),n:ext(overviewView.map(d=>d.n)),pe:ext(overviewView.map(d=>d.pe))};const x=i=>m.l+i/(overviewView.length-1)*cw,y=(v,k)=>m.t+ch-(v-ex[k][0])/(ex[k][1]-ex[k][0])*ch;ctx.clearRect(0,0,w,h);ctx.font='11px Microsoft YaHei';ctx.textBaseline='middle';
for(let i=0;i<=5;i++){const yy=m.t+i*ch/5;ctx.strokeStyle='#1b2c39';ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.textAlign='right';ctx.fillStyle=COLORS.p;ctx.fillText((ex.p[1]-i*(ex.p[1]-ex.p[0])/5).toFixed(1),m.l-8,yy);ctx.textAlign='left';ctx.fillStyle=COLORS.n;ctx.fillText((ex.n[1]-i*(ex.n[1]-ex.n[0])/5).toFixed(0),m.l+cw+8,yy);ctx.fillStyle=COLORS.pe;ctx.fillText((ex.pe[1]-i*(ex.pe[1]-ex.pe[0])/5).toFixed(0),m.l+cw+62,yy)}
for(let i=0;i<=10;i++){const q=Math.round(i*(overviewView.length-1)/10);ctx.fillStyle='#718596';ctx.textAlign='center';ctx.fillText(overviewView[q].d.slice(0,7),x(q),h-17)}
for(const k of ['p','n','pe']){if(!ov[k])continue;ctx.strokeStyle=COLORS[k];ctx.lineWidth=k==='p'?2.1:1.8;ctx.beginPath();overviewView.forEach((d,i)=>i?ctx.lineTo(x(i),y(d[k],k)):ctx.moveTo(x(i),y(d[k],k)));ctx.stroke()}canvas._map={m,cw,ch,x,y}}
overviewRanges.onclick=e=>{if(!e.target.dataset.y)return;oy=+e.target.dataset.y;overviewRanges.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawOverview()};
document.querySelectorAll('[data-overview]').forEach(c=>c.onchange=()=>{ov[c.dataset.overview]=c.checked;drawOverview()});
function overviewHover(ev){const r=overviewChart.getBoundingClientRect(),map=overviewChart._map;if(!map)return;const i=Math.max(0,Math.min(overviewView.length-1,Math.round((ev.clientX-r.left-map.m.l)/map.cw*(overviewView.length-1)))),d=overviewView[i];overviewTip.innerHTML=`<b>${d.d}</b><br><span style="color:${COLORS.p}">股价 ${d.p.toFixed(2)} 元</span><br><span style="color:${COLORS.n}">滚动利润 ${d.n.toFixed(2)} 亿元</span><br><span style="color:${COLORS.pe}">PE ${d.pe.toFixed(2)} 倍</span>`;overviewTip.style.display='block';overviewTip.style.left=Math.min(r.width-190,Math.max(8,ev.clientX-r.left+12))+'px';overviewTip.style.top=Math.max(8,ev.clientY-r.top-75)+'px'}
overviewChart.onmousemove=overviewHover;overviewChart.onmouseleave=()=>overviewTip.style.display='none';
function addPercentile(source,target){const sorted=DATA.map(d=>d[source]).filter(v=>v>0).sort((a,b)=>a-b);DATA.forEach(d=>{let lo=0,hi=sorted.length;while(lo<hi){const mid=(lo+hi)>>1;if(sorted[mid]<=d[source])lo=mid+1;else hi=mid}d[target]=lo/sorted.length*100})}
addPercentile('pe','pe_pct');addPercentile('pb','pb_pct');
let metric='pe',vy=10,valuationView=[];
const metricLabels={pe:'PE(TTM)',pb:'PB',pe_pct:'PE历史分位',pb_pct:'PB历史分位',dy:'股息收益率'};
const metricUnits={pe:'倍',pb:'倍',pe_pct:'%',pb_pct:'%',dy:'%'};
const metricDescriptions={pe:'PE越高，市场对未来盈利增长的要求越高。',pb:'PB反映市值相对净资产的定价，适合结合矿业资产质量与盈利周期观察。',pe_pct:'当前PE在十年样本中的相对位置，越高代表估值越贵。',pb_pct:'当前PB在十年样本中的相对位置，适合辅助观察周期股资产估值。',dy:'股息收益率越高，持有期现金回报通常越有吸引力。'};
const metricColors={pe:'#35bfff',pb:'#ffc84a',pe_pct:'#ff5d73',pb_pct:'#c792ff',dy:'#40df9a'};
function quantile(a,q){const b=a.filter(v=>v>0).sort((x,y)=>x-y),p=(b.length-1)*q,i=Math.floor(p),f=p-i;return b[i]+(b[i+1]??b[i]-b[i])*f}
function valuationSlice(){if(!vy)return DATA;const end=new Date(DATA.at(-1).d),start=new Date(end);start.setFullYear(end.getFullYear()-vy);return DATA.filter(d=>new Date(d.d)>=start)}
function drawNavigator(){const canvas=valuationNavigator;if(!canvas.offsetWidth)return;const {ctx,w,h}=setupCanvas(canvas),vals=DATA.map(d=>d[metric]),ex=metric.endsWith('_pct')?[0,100]:ext(vals,.08),x=i=>i/(DATA.length-1)*w,y=v=>h-4-(v-ex[0])/(ex[1]-ex[0])*(h-8);ctx.clearRect(0,0,w,h);ctx.strokeStyle=metricColors[metric];ctx.lineWidth=1;ctx.beginPath();DATA.forEach((d,i)=>i?ctx.lineTo(x(i),y(d[metric])):ctx.moveTo(x(i),y(d[metric])));ctx.stroke();const ratio=valuationView.length/DATA.length;navigatorWindow.style.width=(ratio*100)+'%'}
function drawValuation(){const canvas=valuationChart;if(!canvas.offsetWidth)return;valuationView=valuationSlice();const vals=valuationView.map(d=>d[metric]).filter(v=>v>=0),{ctx,w,h}=setupCanvas(canvas),m={l:58,r:24,t:25,b:42},cw=w-m.l-m.r,ch=h-m.t-m.b,ex=metric.endsWith('_pct')?[0,100]:ext(vals,.08),x=i=>m.l+i/(valuationView.length-1)*cw,y=v=>m.t+ch-(v-ex[0])/(ex[1]-ex[0])*ch;ctx.clearRect(0,0,w,h);ctx.font='11px Microsoft YaHei';ctx.textBaseline='middle';
for(let i=0;i<=5;i++){const yy=m.t+i*ch/5;ctx.strokeStyle='#1b2c39';ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.fillStyle='#7890a2';ctx.textAlign='right';ctx.fillText((ex[1]-i*(ex[1]-ex[0])/5).toFixed(metric==='pe'?0:1)+metricUnits[metric],m.l-8,yy)}
const guides=metric.endsWith('_pct')?[25,50,75]:[quantile(vals,.25),quantile(vals,.5),quantile(vals,.75)];for(const v of guides){const yy=y(v);ctx.strokeStyle=v===50?'#526f84':'#314a5c';ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.setLineDash([])}
for(let i=0;i<=8;i++){const q=Math.round(i*(valuationView.length-1)/8);ctx.fillStyle='#718596';ctx.textAlign='center';ctx.fillText(valuationView[q].d.slice(0,7),x(q),h-17)}
ctx.strokeStyle=metricColors[metric];ctx.lineWidth=2.1;ctx.beginPath();valuationView.forEach((d,i)=>i?ctx.lineTo(x(i),y(d[metric])):ctx.moveTo(x(i),y(d[metric])));ctx.stroke();canvas._map={m,cw,x,y};const latest=valuationView.at(-1);valuationChartTitle.textContent=metricLabels[metric]+' 长期走势';metricDescription.textContent=metricDescriptions[metric];metricCurrent.textContent='最新：'+metricLabels[metric]+' '+latest[metric].toFixed(2)+metricUnits[metric];drawNavigator()}
metricButtons.onclick=e=>{if(!e.target.dataset.metric)return;metric=e.target.dataset.metric;metricButtons.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawValuation()};
valuationRanges.onclick=e=>{if(e.target.dataset.y===undefined)return;vy=+e.target.dataset.y;valuationRanges.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawValuation()};
valuationChart.onmousemove=e=>{const r=valuationChart.getBoundingClientRect(),map=valuationChart._map;if(!map)return;const i=Math.max(0,Math.min(valuationView.length-1,Math.round((e.clientX-r.left-map.m.l)/map.cw*(valuationView.length-1)))),d=valuationView[i];valuationTip.innerHTML=`<b>${d.d}</b><br><span style="color:${metricColors[metric]}">${metricLabels[metric]}：${d[metric].toFixed(2)} ${metricUnits[metric]}</span>`;valuationTip.style.display='block';valuationTip.style.left=Math.min(r.width-190,Math.max(8,e.clientX-r.left+12))+'px';valuationTip.style.top=Math.max(8,e.clientY-r.top-55)+'px'};valuationChart.onmouseleave=()=>valuationTip.style.display='none';

const HOLDERS=MODEL.holders;
let retailMetric='turn',retailYears=3,retailView=[];
const retailLabels={turn:'换手率',amount:'成交额',small:'小单净流入',rzye:'融资余额',rzbuy:'融资买入占比',holders:'股东户数'};
const retailUnits={turn:'%',amount:'亿元',small:'亿元',rzye:'亿元',rzbuy:'%',holders:'万户'};
const retailColors={turn:'#35bfff',amount:'#ffc84a',small:'#40df9a',rzye:'#c792ff',rzbuy:'#ff6b7d',holders:'#68e0cf'};
const retailDescriptions={turn:'换手率反映筹码交换和市场参与热度。',amount:'成交额反映市场关注度与交易热度，需结合股价方向观察。',small:'小单净流入用于观察小额交易资金方向，单日波动较大。',rzye:'融资余额反映杠杆资金存量，持续上升意味着融资盘参与增强。',rzbuy:'融资买入占比反映当日成交中杠杆买盘的参与程度。',holders:'股东户数来自公司不定期披露；户数上升通常意味着筹码趋于分散。'};
function retailSource(){return retailMetric==='holders'?HOLDERS.map(x=>({d:x.d,v:x.v/10000,ann:x.ann})):DATA.filter(x=>retailMetric!=='rzye'||x.rzye>0).map(x=>({d:x.d,v:x[retailMetric]}))}
function retailSlice(){const source=retailSource();if(!source.length)return [];const end=new Date(source.at(-1).d),start=new Date(end);start.setFullYear(end.getFullYear()-retailYears);return source.filter(x=>new Date(x.d)>=start)}
function signedExt(values,pad=.12){const mn=Math.min(...values),mx=Math.max(...values),p=(mx-mn||1)*pad;return [mn-p,mx+p]}
function drawRetail(){const canvas=retailChart;if(!canvas.offsetWidth)return;retailView=retailSlice();if(!retailView.length)return;const vals=retailView.map(x=>x.v),{ctx,w,h}=setupCanvas(canvas),m={l:68,r:25,t:25,b:44},cw=w-m.l-m.r,ch=h-m.t-m.b,ex=retailMetric==='small'?signedExt(vals):ext(vals,.1),x=i=>m.l+i/Math.max(1,retailView.length-1)*cw,y=v=>m.t+ch-(v-ex[0])/(ex[1]-ex[0])*ch;ctx.clearRect(0,0,w,h);ctx.font='11px Microsoft YaHei';ctx.textBaseline='middle';
for(let i=0;i<=5;i++){const yy=m.t+i*ch/5,val=ex[1]-i*(ex[1]-ex[0])/5;ctx.strokeStyle='#1b2c39';ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.fillStyle='#7890a2';ctx.textAlign='right';ctx.fillText(val.toFixed(retailMetric==='holders'||retailMetric==='amount'||retailMetric==='rzye'?0:1)+retailUnits[retailMetric],m.l-8,yy)}
if(retailMetric==='small'&&ex[0]<0&&ex[1]>0){ctx.strokeStyle='#647c8d';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(m.l,y(0));ctx.lineTo(m.l+cw,y(0));ctx.stroke();ctx.setLineDash([])}
for(let i=0;i<=8;i++){const q=Math.round(i*(retailView.length-1)/8);ctx.fillStyle='#718596';ctx.textAlign='center';ctx.fillText(retailView[q].d.slice(0,7),x(q),h-17)}
ctx.strokeStyle=retailColors[retailMetric];ctx.lineWidth=2.1;ctx.beginPath();retailView.forEach((d,i)=>i?ctx.lineTo(x(i),y(d.v)):ctx.moveTo(x(i),y(d.v)));ctx.stroke();if(retailMetric==='holders'){ctx.fillStyle=retailColors.holders;retailView.forEach((d,i)=>{ctx.beginPath();ctx.arc(x(i),y(d.v),3,0,Math.PI*2);ctx.fill()})}canvas._map={m,cw};const latest=retailView.at(-1);retailChartTitle.textContent=retailLabels[retailMetric]+'长期走势';retailDescription.textContent=retailDescriptions[retailMetric];retailCurrent.textContent='最新：'+latest.v.toFixed(retailMetric==='holders'?1:2)+retailUnits[retailMetric]}
retailMetricButtons.onclick=e=>{if(!e.target.dataset.metric)return;retailMetric=e.target.dataset.metric;retailMetricButtons.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawRetail()};
retailRanges.onclick=e=>{if(!e.target.dataset.y)return;retailYears=+e.target.dataset.y;retailRanges.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawRetail()};
retailChart.onmousemove=e=>{const r=retailChart.getBoundingClientRect(),map=retailChart._map;if(!map)return;const i=Math.max(0,Math.min(retailView.length-1,Math.round((e.clientX-r.left-map.m.l)/map.cw*(retailView.length-1)))),d=retailView[i];retailTip.innerHTML=`<b>${d.d}</b><br><span style="color:${retailColors[retailMetric]}">${retailLabels[retailMetric]}：${d.v.toFixed(retailMetric==='holders'?1:2)} ${retailUnits[retailMetric]}</span>`;retailTip.style.display='block';retailTip.style.left=Math.min(r.width-190,Math.max(8,e.clientX-r.left+12))+'px';retailTip.style.top=Math.max(8,e.clientY-r.top-55)+'px'};retailChart.onmouseleave=()=>retailTip.style.display='none';
const last20=DATA.slice(-20),prev20=DATA.slice(-40,-20),avg=(rows,k)=>rows.reduce((s,x)=>s+x[k],0)/Math.max(1,rows.length),latestHolder=HOLDERS.at(-1),previousHolder=HOLDERS.at(-2);
rTurn.textContent=L.turn.toFixed(2)+'%';rTurnHint.textContent='近20日均值 '+avg(last20,'turn').toFixed(2)+'%';
rAmount.textContent=L.amount.toFixed(1)+' 亿元';rAmountHint.textContent='近20日均值 '+avg(last20,'amount').toFixed(1)+' 亿元';
rSmall.textContent=(L.small>=0?'+':'')+L.small.toFixed(2)+' 亿元';rSmall.style.color=L.small>=0?'var(--green)':'var(--red)';
rMargin.textContent=L.rzye.toFixed(1)+' 亿元';rMarginHint.textContent='近20日变化 '+((L.rzye/DATA.at(-20).rzye-1)*100).toFixed(1)+'%';
rMarginBuy.textContent=L.rzbuy.toFixed(2)+'%';
rHolders.textContent=latestHolder?(latestHolder.v/10000).toFixed(1)+' 万户':'暂无';rHolderHint.textContent=latestHolder?'截至 '+latestHolder.d+(previousHolder?'，较上期 '+((latestHolder.v/previousHolder.v-1)*100).toFixed(1)+'%':''):'';

const HK=MODEL.hk_holds,FUNDS=MODEL.funds,INSTITUTIONS=MODEL.institutions;
let bigMetric='large',bigYears=3,bigView=[];
const bigLabels={large:'大单及超大单净额',hk:'沪股通持股比例',fund_count:'公募基金数量',fund_mkv:'公募基金持仓市值',fund_ratio:'基金流通占比',institution:'前十大机构流通占比'};
const bigUnits={large:'亿元',hk:'%',fund_count:'只',fund_mkv:'亿元',fund_ratio:'%',institution:'%'};
const bigColors={large:'#35bfff',hk:'#ffc84a',fund_count:'#c792ff',fund_mkv:'#40df9a',fund_ratio:'#68e0cf',institution:'#ff8a65'};
const bigDescriptions={large:'大单及超大单净额反映大额交易资金的当日方向。',hk:'沪股通持股比例展示北向资金对紫金矿业的持仓变化。',fund_count:'持有紫金矿业的公募基金数量，按基金报告期汇总。',fund_mkv:'公募基金持有紫金矿业的合计市值，按报告期汇总。',fund_ratio:'各公募基金所持股份占流通股比例的合计值。',institution:'前十大流通股东中非个人股东的流通持股比例合计。'};
function bigSource(){if(bigMetric==='large')return DATA.map(x=>({d:x.d,v:x.large}));if(bigMetric==='hk')return HK.map(x=>({d:x.d,v:x.ratio}));if(bigMetric==='fund_count')return FUNDS.map(x=>({d:x.d,v:x.count}));if(bigMetric==='fund_mkv')return FUNDS.map(x=>({d:x.d,v:x.mkv}));if(bigMetric==='fund_ratio')return FUNDS.map(x=>({d:x.d,v:x.float_ratio}));return INSTITUTIONS.map(x=>({d:x.d,v:x.ratio}))}
function bigSlice(){const source=bigSource();if(!source.length)return [];const end=new Date(source.at(-1).d),start=new Date(end);start.setFullYear(end.getFullYear()-bigYears);return source.filter(x=>new Date(x.d)>=start)}
function drawBig(){const canvas=bigChart;if(!canvas.offsetWidth)return;bigView=bigSlice();if(!bigView.length)return;const vals=bigView.map(x=>x.v),{ctx,w,h}=setupCanvas(canvas),m={l:68,r:25,t:25,b:44},cw=w-m.l-m.r,ch=h-m.t-m.b,ex=bigMetric==='large'?signedExt(vals):ext(vals,.1),x=i=>m.l+i/Math.max(1,bigView.length-1)*cw,y=v=>m.t+ch-(v-ex[0])/(ex[1]-ex[0])*ch;ctx.clearRect(0,0,w,h);ctx.font='11px Microsoft YaHei';ctx.textBaseline='middle';
for(let i=0;i<=5;i++){const yy=m.t+i*ch/5,val=ex[1]-i*(ex[1]-ex[0])/5;ctx.strokeStyle='#1b2c39';ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.fillStyle='#7890a2';ctx.textAlign='right';ctx.fillText(val.toFixed(bigMetric==='fund_count'?0:1)+bigUnits[bigMetric],m.l-8,yy)}
if(bigMetric==='large'&&ex[0]<0&&ex[1]>0){ctx.strokeStyle='#647c8d';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(m.l,y(0));ctx.lineTo(m.l+cw,y(0));ctx.stroke();ctx.setLineDash([])}
for(let i=0;i<=8;i++){const q=Math.round(i*(bigView.length-1)/8);ctx.fillStyle='#718596';ctx.textAlign='center';ctx.fillText(bigView[q].d.slice(0,7),x(q),h-17)}
ctx.strokeStyle=bigColors[bigMetric];ctx.lineWidth=2.1;ctx.beginPath();bigView.forEach((d,i)=>i?ctx.lineTo(x(i),y(d.v)):ctx.moveTo(x(i),y(d.v)));ctx.stroke();if(bigMetric!=='large'){ctx.fillStyle=bigColors[bigMetric];bigView.forEach((d,i)=>{ctx.beginPath();ctx.arc(x(i),y(d.v),3,0,Math.PI*2);ctx.fill()})}canvas._map={m,cw};const latest=bigView.at(-1);bigChartTitle.textContent=bigLabels[bigMetric]+'长期走势';bigDescription.textContent=bigDescriptions[bigMetric];bigCurrent.textContent='最新：'+latest.v.toFixed(bigMetric==='fund_count'?0:2)+bigUnits[bigMetric]}
bigMetricButtons.onclick=e=>{if(!e.target.dataset.metric)return;bigMetric=e.target.dataset.metric;bigMetricButtons.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawBig()};
bigRanges.onclick=e=>{if(!e.target.dataset.y)return;bigYears=+e.target.dataset.y;bigRanges.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawBig()};
bigChart.onmousemove=e=>{const r=bigChart.getBoundingClientRect(),map=bigChart._map;if(!map)return;const i=Math.max(0,Math.min(bigView.length-1,Math.round((e.clientX-r.left-map.m.l)/map.cw*(bigView.length-1)))),d=bigView[i];bigTip.innerHTML=`<b>${d.d}</b><br><span style="color:${bigColors[bigMetric]}">${bigLabels[bigMetric]}：${d.v.toFixed(bigMetric==='fund_count'?0:2)} ${bigUnits[bigMetric]}</span>`;bigTip.style.display='block';bigTip.style.left=Math.min(r.width-190,Math.max(8,e.clientX-r.left+12))+'px';bigTip.style.top=Math.max(8,e.clientY-r.top-55)+'px'};bigChart.onmouseleave=()=>bigTip.style.display='none';
const latestHk=HK.at(-1),previousHk=HK.at(-2),latestFund=FUNDS.at(-1),comparableFund=latestFund?[...FUNDS.slice(0,-1)].reverse().find(x=>x.d.slice(5)===latestFund.d.slice(5)):null,latestInst=INSTITUTIONS.at(-1);
bLarge.textContent=(L.large>=0?'+':'')+L.large.toFixed(2)+' 亿元';bLarge.style.color=L.large>=0?'var(--green)':'var(--red)';
bHk.textContent=latestHk?latestHk.ratio.toFixed(2)+'%':'暂无';bHkHint.textContent=latestHk?'截至 '+latestHk.d+(previousHk?'，较上期 '+(latestHk.ratio-previousHk.ratio).toFixed(2)+'pct':''):'';
bFundCount.textContent=latestFund?latestFund.count+' 只':'暂无';bFundCountHint.textContent=latestFund?'截至 '+latestFund.d+(comparableFund?'，同比 '+(latestFund.count-comparableFund.count)+' 只':''):'';
bFundMkv.textContent=latestFund?latestFund.mkv.toFixed(1)+' 亿元':'暂无';bFundMkvHint.textContent=latestFund?'合计持股 '+latestFund.amount.toFixed(2)+' 亿股':'';
bFundRatio.textContent=latestFund?latestFund.float_ratio.toFixed(2)+'%':'暂无';
bInstitution.textContent=latestInst?latestInst.ratio.toFixed(2)+'%':'暂无';bInstitutionHint.textContent=latestInst?'截至 '+latestInst.d+'，共 '+latestInst.count+' 家非个人股东':'';

const OFFICIAL_HOLDS=MODEL.official_holds,REPURCHASES=MODEL.repurchases,HOLDER_TRADES=MODEL.holder_trades,LPR=MODEL.lpr;
let officialMetric='official_hold',officialYears=10,officialView=[];
const officialLabels={official_hold:'国家队/社保持股比例',repurchase:'累计回购金额',holder_trade:'重要股东累计增减持',lpr1:'1年期LPR',lpr5:'5年期LPR'};
const officialUnits={official_hold:'%',repurchase:'亿元',holder_trade:'%',lpr1:'%',lpr5:'%'};
const officialColors={official_hold:'#c792ff',repurchase:'#ffc84a',holder_trade:'#35bfff',lpr1:'#40df9a',lpr5:'#ff6b7d'};
const officialDescriptions={official_hold:'统计前十大股东中的中国证券金融、中央汇金和社保基金持仓。',repurchase:'展示公司已公告回购计划的累计实施金额。',holder_trade:'重要股东公告增减持比例的历史累计值，增持为正、减持为负。',lpr1:'1年期LPR反映短中期实体融资基准利率环境。',lpr5:'5年期LPR反映中长期融资和地产相关基准利率环境。'};
function officialSource(){if(officialMetric==='official_hold')return OFFICIAL_HOLDS.map(x=>({d:x.d,v:x.ratio}));if(officialMetric==='repurchase')return REPURCHASES.map(x=>({d:x.d,v:x.amount}));if(officialMetric==='holder_trade')return HOLDER_TRADES.map(x=>({d:x.d,v:x.ratio}));if(officialMetric==='lpr1')return LPR.map(x=>({d:x.d,v:x.y1}));return LPR.map(x=>({d:x.d,v:x.y5}))}
function officialSlice(){const source=officialSource();if(!source.length)return [];const end=new Date(source.at(-1).d),start=new Date(end);start.setFullYear(end.getFullYear()-officialYears);return source.filter(x=>new Date(x.d)>=start)}
function drawOfficial(){const canvas=officialChart;if(!canvas.offsetWidth)return;officialView=officialSlice();if(!officialView.length){officialCurrent.textContent='暂无可用记录';return}const vals=officialView.map(x=>x.v),{ctx,w,h}=setupCanvas(canvas),m={l:68,r:25,t:25,b:44},cw=w-m.l-m.r,ch=h-m.t-m.b,ex=officialMetric==='holder_trade'?signedExt(vals):ext(vals,.1),x=i=>m.l+i/Math.max(1,officialView.length-1)*cw,y=v=>m.t+ch-(v-ex[0])/(ex[1]-ex[0])*ch;ctx.clearRect(0,0,w,h);ctx.font='11px Microsoft YaHei';ctx.textBaseline='middle';
for(let i=0;i<=5;i++){const yy=m.t+i*ch/5,val=ex[1]-i*(ex[1]-ex[0])/5;ctx.strokeStyle='#1b2c39';ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+cw,yy);ctx.stroke();ctx.fillStyle='#7890a2';ctx.textAlign='right';ctx.fillText(val.toFixed(2)+officialUnits[officialMetric],m.l-8,yy)}
if(officialMetric==='holder_trade'&&ex[0]<0&&ex[1]>0){ctx.strokeStyle='#647c8d';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(m.l,y(0));ctx.lineTo(m.l+cw,y(0));ctx.stroke();ctx.setLineDash([])}
for(let i=0;i<=8;i++){const q=Math.round(i*(officialView.length-1)/8);ctx.fillStyle='#718596';ctx.textAlign='center';ctx.fillText(officialView[q].d.slice(0,7),x(q),h-17)}
ctx.strokeStyle=officialColors[officialMetric];ctx.lineWidth=2.1;ctx.beginPath();officialView.forEach((d,i)=>i?ctx.lineTo(x(i),y(d.v)):ctx.moveTo(x(i),y(d.v)));ctx.stroke();ctx.fillStyle=officialColors[officialMetric];officialView.forEach((d,i)=>{ctx.beginPath();ctx.arc(x(i),y(d.v),3,0,Math.PI*2);ctx.fill()});canvas._map={m,cw};const latest=officialView.at(-1);officialChartTitle.textContent=officialLabels[officialMetric]+'长期走势';officialDescription.textContent=officialDescriptions[officialMetric];officialCurrent.textContent='最新：'+latest.v.toFixed(2)+officialUnits[officialMetric]}
officialMetricButtons.onclick=e=>{if(!e.target.dataset.metric)return;officialMetric=e.target.dataset.metric;officialMetricButtons.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawOfficial()};
officialRanges.onclick=e=>{if(!e.target.dataset.y)return;officialYears=+e.target.dataset.y;officialRanges.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===e.target));drawOfficial()};
officialChart.onmousemove=e=>{const r=officialChart.getBoundingClientRect(),map=officialChart._map;if(!map)return;const i=Math.max(0,Math.min(officialView.length-1,Math.round((e.clientX-r.left-map.m.l)/map.cw*(officialView.length-1)))),d=officialView[i];officialTip.innerHTML=`<b>${d.d}</b><br><span style="color:${officialColors[officialMetric]}">${officialLabels[officialMetric]}：${d.v.toFixed(2)} ${officialUnits[officialMetric]}</span>`;officialTip.style.display='block';officialTip.style.left=Math.min(r.width-190,Math.max(8,e.clientX-r.left+12))+'px';officialTip.style.top=Math.max(8,e.clientY-r.top-55)+'px'};officialChart.onmouseleave=()=>officialTip.style.display='none';
const latestRepurchase=REPURCHASES.at(-1),latestTrade=HOLDER_TRADES.at(-1),latestOfficial=OFFICIAL_HOLDS.at(-1),latestLpr=LPR.at(-1);
oRepurchase.textContent=latestRepurchase?latestRepurchase.amount.toFixed(2)+' 亿元':'暂无';oRepurchaseHint.textContent=latestRepurchase?latestRepurchase.proc+'，公告日 '+latestRepurchase.d:'近十年无回购记录';
oHolderTrade.textContent=latestTrade?(latestTrade.ratio>=0?'+':'')+latestTrade.ratio.toFixed(2)+'%':'暂无';oHolderTrade.style.color=latestTrade&&latestTrade.ratio>=0?'var(--green)':'var(--red)';oHolderTradeHint.textContent=latestTrade?'最近：'+latestTrade.holder:'近十年无重要股东增减持记录';
oOfficialHold.textContent=latestOfficial?latestOfficial.ratio.toFixed(2)+'%':'暂无';oOfficialHoldHint.textContent=latestOfficial?'截至 '+latestOfficial.d+'，'+latestOfficial.count+' 个账户':'前十大股东未发现国家队/社保';
oLpr.textContent=latestLpr?latestLpr.y1.toFixed(2)+'% / '+latestLpr.y5.toFixed(2)+'%':'暂无';oLprHint.textContent=latestLpr?'截至 '+latestLpr.d:'';
forecastGrid.innerHTML=Object.entries(MODEL.consensus).map(([year,x])=>`<div class="forecast"><div class="label">${year} 年</div><strong>${x.forward_pe?.toFixed(2)??'-'} 倍 PE</strong><div class="bar"><span style="width:${Math.min(100,(x.eps/5)*100)}%"></span></div><div>EPS 中位数 ${x.eps?.toFixed(2)??'-'} 元</div><div class="hint">${x.count} 家机构｜区间 ${x.eps_low}–${x.eps_high} 元<br>净利润中位数 ${x.np?.toFixed(0)??'-'} 亿元</div></div>`).join('');
function eventQuarter(date){return Math.floor((Number(date.slice(4,6))-1)/3)+1}
function setupEventFilter(data,yearSelect,quarterSelect,container){
 const sorted=[...data].sort((a,b)=>b.date.localeCompare(a.date)),latest=sorted[0],years=[...new Set(sorted.map(x=>x.date.slice(0,4)))];
 yearSelect.innerHTML=years.map(y=>`<option value="${y}">${y}</option>`).join('');
 quarterSelect.innerHTML=[1,2,3,4].map(q=>`<option value="${q}">Q${q}</option>`).join('');
 if(latest){yearSelect.value=latest.date.slice(0,4);quarterSelect.value=String(eventQuarter(latest.date))}
 const render=()=>{const rows=sorted.filter(x=>x.date.startsWith(yearSelect.value)&&eventQuarter(x.date)===Number(quarterSelect.value));container.innerHTML=rows.length?rows.map(x=>`<div class="event"><div class="date">${x.date.slice(0,4)}-${x.date.slice(4,6)}-${x.date.slice(6)}</div>${x.text}</div>`).join(''):'<div class="empty-event">该季度暂无事件记录</div>'};
 yearSelect.onchange=render;quarterSelect.onchange=render;render();
}
setupEventFilter(MODEL.events,valuationEventYear,valuationEventQuarter,events);
setupEventFilter(MODEL.sentiment_events,retailEventYear,retailEventQuarter,sentimentEvents);
setupEventFilter(MODEL.big_events,bigEventYear,bigEventQuarter,bigEvents);
setupEventFilter(MODEL.official_events,officialEventYear,officialEventQuarter,officialEvents);
reports.innerHTML=MODEL.reports.map(x=>`<tr><td>${x.date.slice(0,4)}-${x.date.slice(4,6)}-${x.date.slice(6)}</td><td>${x.org}</td><td>${x.title}</td><td><span class="pill">${x.rating}</span></td></tr>`).join('');
addEventListener('resize',()=>{drawOverview();drawValuation();drawRetail();drawBig();drawOfficial()});drawOverview();drawValuation();drawRetail();drawBig();drawOfficial();
</script></body></html>"""


def main():
    model = build_data(get_token())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    html = HTML.replace(
        "__MODEL__", json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    )
    OUTPUT.write_text(html, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "points": len(model["series"]),
                "latest": model["latest"],
                "consensus": model["consensus"],
                "target": model["target"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
