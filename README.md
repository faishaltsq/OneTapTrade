# OneTapTrade

OneTapTrade sekarang adalah **TradingView signal assistant**. Aplikasi ini menerima alert TradingView, membaca chart lokal melalui TradingView MCP, mengambil screenshot chart, menjalankan analisis AI opsional, lalu mengirim hasilnya ke Telegram.

Project ini **bukan auto-trading executor**. Tidak ada eksekusi order, tidak ada koneksi MetaTrader, dan tidak ada live trading.

## Progress Saat Ini

- TradingView webhook signal-only aktif.
- TradingView MCP runtime terhubung ke FastAPI server.
- TradingView Desktop Microsoft Store bisa auto-launch saat server start.
- Server bisa switch chart ke pair/timeframe target sebelum screenshot.
- Screenshot chart dikirim ke Telegram untuk setiap analisis.
- Screenshot chart sudah dilebarkan agar price scale kanan ikut terlihat.
- Telegram bot command polling + inline keyboard + callback query aktif.
- `/scan` command (alias `/analyze`) multi-pair day-trade scan dengan channel broadcast.
- Telegram channel broadcast: setup valid dikirim ke `TELEGRAM_CHANNEL_ID` dengan caption lengkap.
- Admin summary: grouped no-setup pairs, low confidence, cooldown, dan error setelah scan.
- DeepSeek OpenAI-compatible chat completion didukung melalui `AI_API_KEY`.
- AI day-trade setup scanner: 8 setup types (BUY/SELL MARKET/LIMIT/STOP, WAIT, NO_SETUP).
- Analisa teknikal: EMA 50/200, SMC LuxAlgo, BOS/CHoCH/liquidity sweep/OB/supply-demand/FVG, HTF SNR (H4/D).
- Prediction drawing di chart TradingView: risk/reward box, Entry/SL/TP1/TP2 line, label LONG/SHORT.
- Automatic signal scanner background dengan confidence filter, RR filter, screenshot requirement, cooldown per symbol/action/setup_type.
- Max broadcast per scan limit (`AUTO_SIGNAL_MAX_BROADCAST_PER_SCAN=3`) mencegah spam channel.
- Format-repair retry: jika output AI tidak bisa diparse, retry sekali dengan prompt formatting tanpa re-analyze.
- Telegram caption >1000 chars di-split: foto + short caption, full detail sebagai pesan terpisah.
- Scan history logging ke `data/scan_history.json` (200 entries max).
- 11 default pairs: forex majors, crypto COINBASE, USOIL, NAS100.
- Fitur lama sudah dihapus: MT5, auto trade, execution, Supabase, risk manager, trading loop, DeepSeek executor lama.

## Fitur Aktif

- `POST /tradingview/webhook` menerima alert TradingView.
- `GET /tradingview/last-signal` melihat signal terakhir.
- `GET /analysis/chart-context` mengambil status chart, quote, OHLCV summary, indicator values, dan screenshot.
- `POST /analysis/chart` menjalankan analisis chart dari context TradingView MCP.
- Telegram command `/scan`, `/analyze`, `/status`, `/last_signal`, `/help` — semua reply dengan inline keyboard.
- Telegram inline keyboard: tombol `Scan`, `Status`, `Last Signal`, `Help / Menu`.
- `/scan` dan `/analyze`: scan semua pair, broadcast valid setup ke channel, admin summary.
- Scan loading: `sendChatAction` typing + scanning message, hasil dikirim satu per satu.
- Multi-pair scan dari daftar `DEFAULT_SYMBOLS`.
- Optional AI analysis via DeepSeek-compatible API.
- AI day-trade method: 8 setup types, EMA 50/200, SMC LuxAlgo, HTF SNR dari H4/D.
- Channel broadcast: hanya BUY/SELL yang lolos confidence, RR, screenshot, day-trade check.
- Admin summary: grouped no-setup, low confidence, cooldown, error pairs.
- Prediction drawing: box dan line Entry/SL/TP di chart TradingView untuk setiap BUY/SELL valid.
- Automatic signal scanner: scan background interval, broadcast ke channel, admin summary.
- 11 default symbols: OANDA forex + COINBASE crypto + TVC USOIL + OANDA NAS100.

## Prasyarat

- Windows.
- Python 3.12+.
- Node.js 18+.
- TradingView Desktop dari Microsoft Store.
- Repo `tradingview-mcp` lokal sebagai runtime chart/screenshot bridge.
- Telegram bot token dari BotFather jika ingin notifikasi Telegram.
- DeepSeek API key jika ingin analisis AI aktif.

Path TradingView Microsoft Store yang dipakai saat ini:

```text
C:\Program Files\WindowsApps\31178TradingViewInc.TradingView_3.2.0.0_x64__q4jpyh43s5mv6\TradingView.exe
```

## Instalasi Dari Nol

Clone OneTapTrade:

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects
git clone https://github.com/faishaltsq/OneTapTrade.git
cd OneTapTrade
```

Buat virtual environment Python:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Clone TradingView MCP di folder sibling:

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects
git clone https://github.com/tradesdontlie/tradingview-mcp.git
cd tradingview-mcp
npm install
```

Requirement penting untuk `tradingview-mcp`:

- Folder default yang dibaca app adalah `../tradingview-mcp` dari root OneTapTrade.
- FastAPI memanggil MCP via CLI, jadi dependency ini tetap wajib walaupun OpenCode MCP belum aktif.
- Fresh clone upstream perlu local compatibility patch agar cocok dengan setup ini: Microsoft Store TradingView path, custom CDP port `9222`, health check dari `TRADINGVIEW_APP_PATH`, dan screenshot chart yang melebar sampai price scale kanan.
- Di mesin ini patch lokal sudah ada di repo sibling `C:\Users\cubeb\OneDrive\Documents\projects\tradingview-mcp`.

Kembali ke app:

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects\OneTapTrade
```

## Konfigurasi `.env`

Isi `.env` dari template ini:

```env
APP_ENV=development
APP_NAME=OneTapTrade

DEFAULT_SYMBOL=XAUUSD
DEFAULT_SYMBOLS=OANDA:XAUUSD,OANDA:EURUSD,OANDA:GBPUSD,OANDA:USDJPY,OANDA:GBPJPY,OANDA:NZDUSD,TVC:USOIL,OANDA:NAS100USD,COINBASE:BTCUSD,COINBASE:ETHUSD,COINBASE:SOLUSD
DEFAULT_TIMEFRAME=60

TRADINGVIEW_WEBHOOK_SECRET=isi-secret-sendiri
TRADINGVIEW_MCP_DIR=../tradingview-mcp
TRADINGVIEW_MCP_NODE=node
TRADINGVIEW_MCP_TIMEOUT_SECONDS=30
TRADINGVIEW_APP_PATH=C:\Program Files\WindowsApps\31178TradingViewInc.TradingView_3.2.0.0_x64__q4jpyh43s5mv6\TradingView.exe
TRADINGVIEW_CDP_PORT=9222
TRADINGVIEW_SMC_STUDY_FILTER=Smart Money
TRADINGVIEW_EMA_BAR_COUNT=250
TRADINGVIEW_SNR_TIMEFRAMES=240,D
TRADINGVIEW_SNR_BAR_COUNT=200
AUTO_LAUNCH_TRADINGVIEW_ON_STARTUP=true
CAPTURE_CHART_ON_SIGNAL=true
PREDICTION_DRAWING_ENABLED=true
PREDICTION_DRAWING_BARS_AHEAD=24

AI_API_KEY=
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-pro
AI_ANALYSIS_ON_SIGNAL=false
AI_TRADING_STYLE=forex_daytrade
AI_MIN_TRADE_CONFIDENCE=70
AI_MIN_RR=1.5

AUTO_SIGNAL_ENABLED=false
AUTO_SIGNAL_INTERVAL_MINUTES=15
AUTO_SIGNAL_TIMEFRAME=
AUTO_SIGNAL_MIN_CONFIDENCE=70
AUTO_SIGNAL_SEND_WAIT=false
AUTO_SIGNAL_COOLDOWN_MINUTES=60
AUTO_SIGNAL_MAX_BROADCAST_PER_SCAN=3
DAY_TRADE_ONLY=true

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=
TELEGRAM_COMMAND_POLLING_ENABLED=true
```

Catatan keamanan:

- Jangan commit `.env`.
- `.env` sudah di-ignore oleh Git.
- Isi `TRADINGVIEW_WEBHOOK_SECRET` dengan string random saat memakai public tunnel.

Catatan DeepSeek AI:

- `/scan` memakai DeepSeek otomatis jika `AI_API_KEY` terisi.
- Webhook TradingView memakai DeepSeek otomatis jika `AI_ANALYSIS_ON_SIGNAL=true`.
- `AI_TRADING_STYLE=forex_daytrade` mengaktifkan prompt khusus forex day-trade.
- `AI_MIN_TRADE_CONFIDENCE=70` dan `AI_MIN_RR=1.5` membuat AI lebih selektif: jika setup tidak memenuhi kualitas minimum, output harus `WAIT`.
- Jika chart punya EMA 50/200 dan SMC, TradingView MCP akan memakai `values` plus Pine `lines`, `labels`, dan `boxes` dari study yang cocok dengan `TRADINGVIEW_SMC_STUDY_FILTER`.
- Setup chart saat ini terdeteksi punya `EMA 20/50/100/200` dan `Smart Money Concepts [LuxAlgo]`; data ini dipakai sebagai tambahan confluence day-trade.
- EMA 50/200 juga dihitung langsung dari OHLCV TradingView memakai `TRADINGVIEW_EMA_BAR_COUNT`, jadi tetap tersedia walaupun indikator EMA protected hanya expose satu `Plot` di data window.
- SNR hanya dihitung dari high timeframe yang ada di `TRADINGVIEW_SNR_TIMEFRAMES`, default `240,D`, agar level valid untuk day-trade dan tidak terlalu noise dari TF entry.
- Jika hasil analisa punya `BUY`/`SELL` dengan Entry, SL, dan TP valid, app menggambar prediction setup di chart TradingView: reward box, risk box, line Entry, SL, TP1, TP2, dan label LONG/SHORT.
- `PREDICTION_DRAWING_BARS_AHEAD` mengatur panjang projection ke kanan chart. App tidak menghapus drawing lama otomatis agar tidak merusak drawing manual.
- AI membantu meningkatkan selektivitas signal, tetapi tidak menjamin profit atau win-rate tertentu.

Catatan automatic signal:

- Aktifkan dengan `AUTO_SIGNAL_ENABLED=true`.
- Wajib ada `AI_API_KEY`, `TELEGRAM_BOT_TOKEN`, dan `TELEGRAM_ALLOWED_CHAT_ID`.
- Scanner otomatis menjalankan analisa semua `DEFAULT_SYMBOLS` setiap `AUTO_SIGNAL_INTERVAL_MINUTES`.
- `AUTO_SIGNAL_TIMEFRAME` kosong berarti pakai `DEFAULT_TIMEFRAME`; isi misalnya `15` atau `60` jika ingin override.
- Default hanya kirim `BUY`/`SELL` dengan confidence minimal `AUTO_SIGNAL_MIN_CONFIDENCE`; `WAIT` tidak dikirim kecuali `AUTO_SIGNAL_SEND_WAIT=true`.
- `AUTO_SIGNAL_COOLDOWN_MINUTES` mencegah spam signal yang sama untuk symbol:action:setup_type yang sama.
- `AUTO_SIGNAL_MAX_BROADCAST_PER_SCAN=3` membatasi maksimal broadcast per scan ke channel.

## Menjalankan Server

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects\OneTapTrade
.\.venv\Scripts\Activate.ps1
python run.py
```

Saat server start, aplikasi akan:

- membuka TradingView Desktop otomatis jika belum aktif,
- mengaktifkan CDP port `9222`,
- menunggu TradingView chart API siap,
- menjalankan Telegram command polling jika token/chat id tersedia.

Cek health:

```powershell
Invoke-WebRequest "http://localhost:8000/health" -UseBasicParsing
```

Cek TradingView MCP dari server:

```powershell
Invoke-WebRequest "http://localhost:8000/analysis/chart-context?symbol=OANDA:XAUUSD&timeframe=60" -UseBasicParsing
```

## Telegram Commands

Command yang aktif:

```text
/scan         ← main command, scan semua configured pairs
/status
/last_signal
/help
```

Alias:

```text
/analyze      ← alias untuk /scan
/analysis     ← alias untuk /scan
/menu
```

Semua command reply balik dengan inline keyboard:

- `Scan` dan `Status` di satu baris.
- `Last Signal` dan `Help / Menu` di baris kedua.

Tombol `Scan` mengirim `sendChatAction` typing dan scanning message sebelum chart scan berjalan. Hasil valid di-broadcast ke channel Telegram, admin mendapat summary.

### Channel Broadcast

Jika `TELEGRAM_CHANNEL_ID` diisi:

- Setup valid BUY/SELL dikirim sebagai foto ke channel dengan caption lengkap.
- WAIT dan NO_SETUP tidak dibroadcast ke channel.
- Admin mendapat grouped summary setelah setiap scan.

Format caption channel:

```text
AI DAY TRADE SETUP — {PAIR}
Setup Type: {setup_type}
Entry: {entry}
Stop Loss: {sl}
Take Profit: TP1: {tp1} TP2: {tp2}
Market Bias: {bias} Confidence: {confidence}%
Risk Reward: {risk_reward}
AI Reason: {reason}
Invalidation: {invalidation}
Risk Reminder: Gunakan lot sesuai manajemen risiko.
```

### Admin Summary

Setelah scan selesai, admin menerima:

```text
AI DAY-TRADE MULTI-PAIR SCAN SUMMARY
Timeframe: {timeframe}
Scanned: {total} pairs
Broadcasted Setups: {count}
Setup Pairs: {list}
No Valid Setup: {count}
Low Confidence: {list}
Skipped by Cooldown: {list}
Result: {summary sentence}
```

Analisis semua pair dari `DEFAULT_SYMBOLS`:

```text
/analyze
```

Analisis pair tertentu:

```text
/analyze OANDA:XAUUSD,OANDA:EURUSD tf=60
```

Contoh analisis crypto:

```text
/analyze COINBASE:BTCUSD,COINBASE:ETHUSD,COINBASE:SOLUSD tf=60
```

Contoh analisis oil, Nasdaq, dan forex tambahan:

```text
/analyze TVC:USOIL,OANDA:NAS100USD,OANDA:GBPJPY,OANDA:NZDUSD tf=60
```

Setiap pair akan:

- switch chart TradingView ke symbol/timeframe target,
- ambil screenshot chart,
- ambil quote dan OHLCV summary,
- menjalankan AI analysis jika `AI_API_KEY` tersedia,
- mengirim screenshot + hasil analisis ke Telegram.

Automatic signal memakai alur yang sama dengan `/analyze`, tetapi berjalan background saat server menyala dan hanya mengirim signal yang lolos filter confidence/cooldown.

Jika prediction drawing aktif, screenshot Telegram untuk `/analyze`, webhook, dan automatic signal akan diambil ulang setelah drawing dibuat supaya setup long/short terlihat di gambar.

## Format Pesan Analisis

Output signal memakai format ini:

```text
⚪ {PAIR} — {BUY / SELL / WAIT}

Bias: {Bullish/Bearish/Neutral}
Confidence: {0–100}%

Entry: {WAIT / MARKET / LIMIT + harga / area entry}
SL: {harga SL}
TP1: {harga TP1}
TP2: {harga TP2}

Reason:
{Alasan singkat AI dalam 1–2 kalimat.}

Invalid jika:
{syarat setup batal}

Risk:
Gunakan lot sesuai manajemen risiko.
```

Jika AI tidak aktif atau gagal:

- Untuk `WAIT`, output memakai `Entry: WAIT - no trade`, `SL: N/A`, `TP1: N/A`, `TP2: N/A`.
- Untuk webhook `BUY` atau `SELL`, fallback akan membuat level dasar dari range chart terakhir agar tidak menulis placeholder manual.

Metode AI DeepSeek untuk forex day-trade:

- Filter bias dari trend, market structure, support/resistance, dan kondisi momentum.
- Gunakan EMA 50/200 sebagai trend filter: BUY lebih valid saat harga dan EMA 50 berada di atas EMA 200, SELL lebih valid saat harga dan EMA 50 berada di bawah EMA 200.
- Gunakan SMC sebagai confluence: BOS, CHoCH, EQH/EQL, order-block/supply-demand boxes, dan level horizontal terdekat.
- Gunakan SNR high timeframe saja sebagai validasi: hindari BUY langsung di bawah resistance H4/D dan hindari SELL langsung di atas support H4/D kecuali ada breakout-retest atau sweep/rejection yang jelas.
- Cari entry continuation setelah pullback atau breakout-retest; reversal hanya jika ada liquidity sweep dan rejection yang jelas.
- Hindari entry yang terlambat, chasing, sideways/chop, atau terlalu jauh dari invalidation.
- Hindari BUY langsung ke liquidity/resistance bearish terdekat atau SELL langsung ke support/demand bullish terdekat.
- SL harus berada di luar struktur invalidation, bukan jarak acak.
- TP1 target level terdekat yang realistis; TP2 target struktur/liquidity berikutnya.
- BUY/SELL hanya jika confidence minimal sesuai `AI_MIN_TRADE_CONFIDENCE` dan reward:risk minimal sesuai `AI_MIN_RR`; selain itu `WAIT`.

## TradingView Webhook

Endpoint lokal:

```text
http://localhost:8000/tradingview/webhook
```

Contoh alert JSON TradingView:

```json
{
  "secret": "isi-secret-sendiri",
  "symbol": "{{ticker}}",
  "action": "buy",
  "price": "{{close}}",
  "timeframe": "{{interval}}",
  "message": "TradingView signal"
}
```

Field yang dikenali:

- `secret`
- `symbol`, `ticker`, atau `pair`
- `action`, `side`, `signal`, `order_action`, atau `strategy_action`
- `price`, `close`, `entry`, atau `entry_price`
- `timeframe`, `interval`, atau `tf`
- `message`, `text`, atau `comment`
- `sl` atau `stop_loss`
- `tp`, `tp1`, `take_profit`, atau `take_profit_1`
- `tp2` atau `take_profit_2`

TradingView cloud alerts tidak bisa memanggil `localhost` langsung. Untuk alert live, gunakan public HTTPS tunnel seperti ngrok atau cloudflared.

## OpenCode MCP

`opencode.json` sudah mengarah ke MCP lokal:

```text
C:\Users\cubeb\OneDrive\Documents\projects\tradingview-mcp
```

Setelah mengubah `opencode.json`, restart OpenCode agar MCP tools masuk ke session. Runtime FastAPI tetap bisa memakai TradingView MCP melalui CLI walaupun OpenCode belum direstart.

## Testing

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects\OneTapTrade
.\.venv\Scripts\Activate.ps1
pytest
```

Status terakhir:

```text
17 passed
```

## Troubleshooting

Jika port `8000` sudah dipakai:

```powershell
Get-NetTCPConnection -LocalPort 8000
```

Jika TradingView sudah terbuka tanpa debug port, server akan restart proses TradingView saat perlu. Kamu juga bisa launch manual:

```powershell
cd C:\Users\cubeb\OneDrive\Documents\projects\tradingview-mcp
scripts\launch_tv_debug.bat 9222
```

Jika Telegram command tidak merespons:

- Pastikan `TELEGRAM_BOT_TOKEN` benar.
- Pastikan `TELEGRAM_ALLOWED_CHAT_ID` benar.
- Restart server setelah mengubah `.env`.
- Kirim `/help` ke bot.

Jika AI tidak memberi analisis:

- Isi `AI_API_KEY`.
- Pastikan `AI_BASE_URL=https://api.deepseek.com`.
- Pastikan `AI_MODEL=deepseek-v4-pro` tersedia di akun DeepSeek kamu.
- Set `AI_ANALYSIS_ON_SIGNAL=true` jika ingin analisis otomatis saat webhook masuk.

## Catatan Risiko

Output aplikasi ini adalah bantuan analisis signal-only. Tidak ada jaminan profit dan tidak ada eksekusi order otomatis. Gunakan lot sesuai manajemen risiko pribadi.
