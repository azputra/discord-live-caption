# Discord Live Caption & Translate

A desktop app for Discord voice meetings. It captions what you hear and what you say, translates between Indonesian and English while the meeting is going, and keeps the whole transcript until you stop. You can copy or export that transcript and paste it into an AI tool for a summary.

Windows and macOS are both first-class. The audio backend is chosen from the operating system. Speech recognition, translation, the window, and storage are shared.

```text
python -m app.main
```

Run that from the project directory after the setup for your OS.

## Requirements

- Python 3.11 or newer
- A microphone
- On macOS, [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole) so the app can hear Discord
- Optional API keys in `.env` if you use OpenAI or Anthropic

The default speech engine is local Faster Whisper (`small`). The default translator is an LLM. Neither is called until you press Start, and the window opens without API keys.

## Windows setup

1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/windows/) and check "Add python.exe to PATH".
2. In a terminal:

```bat
cd discord-live-caption
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.main
```

`requirements.txt` installs `pyaudiowpatch` only on Windows. That package is the WASAPI loopback capture used for system audio.

### Pick the loopback device

1. Leave Discord playing through your normal speakers or headphones.
2. In this app, click Refresh.
3. The system-audio list shows WASAPI loopback endpoints. Choose the one that matches the output Discord is using. It often looks like `Speakers (Realtek) [Loopback]`.
4. Choose your microphone in the other list.
5. Press Start. The Others meter should move when someone else speaks. The Me meter should move when you speak.

You do not need Stereo Mix when WASAPI loopback is available.

### Use it with Discord

Join the voice channel the way you usually do. This app does not join as a bot and does not ask Discord for permission. It listens to the same output you hear, plus your microphone. Per-person names are not detected; other people are labeled as one source.

## macOS setup

1. Install Python 3.11+ (Homebrew `python@3.13` or python.org).
2. Install BlackHole 2ch:

```bash
brew install --cask blackhole-2ch
```

Or install the pkg from [Existential Audio](https://github.com/ExistentialAudio/BlackHole). If the device does not appear, log out and back in.

3. Create a virtual environment and start the app:

```bash
cd discord-live-caption
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

`pyobjc-framework-Cocoa` is installed only on macOS. It lets the overlay sit above normal windows and many full-screen spaces.

### Audio MIDI Setup

macOS does not offer a loopback of "what you hear" by itself. BlackHole is a virtual input. A Multi-Output Device lets you hear the meeting and record it at the same time.

1. Open **Audio MIDI Setup** (Applications > Utilities).
2. Click **+** and choose **Create Multi-Output Device**.
3. Check your speakers or headphones **and** BlackHole 2ch.
4. Leave BlackHole's volume at full. If you see Drift Correction, enable it on BlackHole.
5. In Discord, open **Voice & Video** and set the output device to that Multi-Output Device. You can instead set the macOS system output to it, which also covers Discord.
6. In this app, click **Refresh** and select **BlackHole 2ch** as system audio. Select your real microphone in the other list.
7. Grant **Microphone** access to Terminal, your IDE, or the app in **System Settings > Privacy & Security > Microphone**. BlackHole is an input device, so macOS asks for microphone permission even for meeting audio.

### Volume caveat

You hear other people through the speaker device inside the Multi-Output Device, not through BlackHole. The menu-bar volume slider often does not control that mix. Change the speaker level in Audio MIDI Setup. Do not turn BlackHole down. If you do, the captions receive quiet audio even when the meeting still sounds loud to you.

If BlackHole is missing, the app does not fail silently. The system-audio selector stays empty and a setup hint is shown. Other virtual devices whose names contain Loopback or Soundflower are still listed, and the hint remains until BlackHole itself is detected.

## Day to day

Press **Start** to open a session and **Stop** to end it. Captions stay on screen for the whole session. Each line has a timestamp and a source, **Me** or **Others** (or the Indonesian labels when the UI language is Indonesian).

- **Speech**: Auto, Indonesian, or English. Auto detects the language of each segment. A manual choice forces that language for the following captions.
- **Translation**: **Swap** (default) turns Indonesian into English and English into Indonesian. **Fixed target** translates everything into the language you pick, and leaves text that is already in that language unchanged. A segment is never translated into the language it is already in.
- **Display**: original, translation, or both. The original line shows up immediately. The translation is filled in underneath when it is ready.
- The feed follows the latest line. Scroll up and auto-scroll pauses. **Jump to latest** returns to the bottom.
- **Overlay** opens a frameless, always-on-top window you can drag and resize. Opacity and font size are on that window. Put it over Discord. macOS uses a high window level and joins spaces where the OS allows it. Windows reapplies `HWND_TOPMOST`. Exclusive full-screen and some protected surfaces can still cover it.
- **Copy transcript**, **Copy translation**, and **Copy both** put the current session on the clipboard.
- **Single language** chooses Indonesian or English for **Copy single language**, **Copy for AI summary**, and the single-language export. Where the original is already in that language, the original is used. Otherwise the translation is used.
- **Copy for AI summary** copies this instruction, then the single-language transcript with timestamps and speaker labels:

```text
Summarize this meeting: key points, decisions, action items with owners, open questions.
```

- **Summarize** sends that same prompt to the configured LLM and shows the result. Mock mode returns a local stand-in so you can try the button without a key.
- **Export** writes `.txt`, `.md`, or `.json`. JSON includes the timestamp, source, detected language, original text, and translated text.
- **History** opens past sessions for reading, copying, and export. Stopping a session does not delete it.
- **Settings** chooses the speech provider, Whisper model size (`small` or `medium`), translation provider, LLM vendor, and whether to save audio. API key fields show whether a key is set. Leave a key field blank to keep the saved key. Provider changes apply on the next Start. Speech language and translation mode apply to the next caption.

UI language and theme (system, light, dark) are on the main window.

## Switch providers

In `config.yaml`, or in Settings:

| Goal | `stt.provider` | `translation.provider` |
| --- | --- | --- |
| Local captions, LLM translation (default) | `faster-whisper` | `llm` |
| Cloud captions | `openai` | `llm` |
| Offline translation | `faster-whisper` | `argos` |
| UI and pipeline test, no hardware and no keys | `mock` | `mock` |

`translation.llm_vendor` is `openai` or `anthropic`. Models default to `gpt-4o-mini` and `claude-3-5-haiku-latest`.

Put keys in `.env` next to `config.yaml`:

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

Faster Whisper downloads the `small` model the first time you transcribe (hundreds of megabytes, cached by Hugging Face). On a CUDA GPU it uses float16. On every other machine, including Apple Silicon, it uses CPU int8. `medium` is available in Settings and is slower on CPU.

Voice activity detection tries Silero first, then webrtcvad, then a built-in energy detector. webrtcvad has no wheel for Python 3.13, so that fallback is only installed on older Python. The app keeps running on the energy detector if the others cannot load.

Argos downloads the Indonesian/English packages the first time you translate offline.

Audio is resampled to 16 kHz mono before VAD and speech recognition, whatever rate the device uses. Audio files are not saved unless **Save audio** is on. Those WAV files go in the per-user data directory, one for Me and one for Others.

Typical paths:

| | macOS | Windows |
| --- | --- | --- |
| Database | `~/Library/Application Support/discord-live-caption/` | `%LOCALAPPDATA%\azputra\discord-live-caption\` |
| Logs | `~/Library/Logs/discord-live-caption/app.log` | `%LOCALAPPDATA%\azputra\discord-live-caption\Logs\app.log` |

Settings shows the exact paths on your machine. Logs rotate at about 2 MB, with five backups.

## Tests

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pytest
```

The tests cover translation direction (swap, fixed target, never same-language), the pipeline with mock speech and mock translation, SQLite, export, device selection, and platform selection with `sys.platform` patched. A UI test drives the window offscreen with a fake audio device, so it does not open your microphone.

Set both providers to `mock` if you want to click through the real window without a model download or an API key.

## Troubleshooting

**No audio / meters stay at zero**

- Press Refresh and confirm the system device is the loopback (WASAPI on Windows, BlackHole on macOS), not your speakers as a normal input.
- On macOS, Discord's output must be the Multi-Output Device that includes BlackHole. If Discord is playing only to the speakers, BlackHole hears nothing.
- Confirm the meeting is actually producing sound, then watch the matching meter.
- Start again after you change devices. Device changes apply on the next Start.

**BlackHole is not detected**

- Install the 2ch build, not only the 16ch build. The 2ch device is preferred when both exist, but the hint is based on the name containing "BlackHole".
- Log out and back in, then Refresh.
- In Audio MIDI Setup, confirm a device named BlackHole 2ch exists.
- The hint lists the full setup. The app will not pretend capture is working.

**Microphone permission denied**

- macOS: System Settings > Privacy & Security > Microphone, and enable Terminal, Cursor, or the app you launched.
- Quit and start the app after changing permission. macOS does not apply the grant to a process that is already running.
- Windows: Settings > Privacy > Microphone, and allow desktop apps.

**Transcription is slow**

- Stay on the `small` model on CPU. `medium` is more accurate and much slower.
- Captions are cut with VAD after a short silence (about half a second). Long stretches without a pause produce a longer clip and a later caption.
- The first Start also waits on the model download.
- A CUDA GPU on Windows is used automatically when CTranslate2 can see it. Apple Silicon stays on CPU int8.
- If the cloud transcriber fails, the app retries, then falls back to local Faster Whisper, and keeps recording.

**A translation did not appear**

- The original line is already saved. A failed translation is marked on that line and does not delete it.
- Check the status text and `app.log`.
- Swap and fixed-target both skip a call when the segment is already in the destination language.
- Text that is neither Indonesian nor English is kept and not translated.

## Assumptions

- v1 labels audio as Me (microphone) and Others (system / loopback). It does not identify each person in the Discord channel.
- Launch the app from the project directory, or from any directory whose `config.yaml` should win. If the working directory has no config file, the copy next to the package is used. `.env` is read from that same directory.
- Manual speech language forces the language of the next captions. It is not the translation target. The translation target is Swap, or the Fixed target language.
- If detection returns a language other than Indonesian or English, the caption is stored and translation is skipped.
- Copy Translation uses the original line when a translation is missing, so the export stays a continuous transcript.
- The AI instruction is always the English sentence in the spec. Speaker labels in the copied text follow the UI language.
- Summarize uses the configured LLM. When the translation provider is Mock, Summarize uses the mock summarizer so the UI can be tried without keys.
- Cloud speech recognition retries with backoff, then falls back to local Faster Whisper. Recording does not stop because an API call failed.
- Partial captions update while someone is still talking. Only the final line is written to SQLite.
- Start clears the on-screen feed and opens a new session. The previous session stays in History.
- Empty API key fields do not erase a key already stored in `.env`.
- Known Whisper silence lines such as "Thanks for watching" are dropped, and a high no-speech score is dropped. VAD already avoids sending silence.
- On macOS the expected loopback is BlackHole 2ch. The app does not install audio drivers.
- On Windows, system audio is the WASAPI loopback list from `pyaudiowpatch`.
- The overlay cannot force itself above exclusive full-screen or OS-protected surfaces.

## Layout

```text
app/
  main.py                 entry point
  config.py               config.yaml + .env
  pipeline.py             queues and worker threads
  audio/                  Windows and macOS capture, VAD, devices
  stt/                    Faster Whisper, OpenAI, mock
  translate/              LLM, Argos, mock, direction rules
  storage/                SQLite and export
  ui/                     main window, overlay, settings, history, locales
tests/
```

Audio capture never runs on the UI thread. Stages pass `AudioChunk` and `TranscriptSegment` values through queues. The window updates only through Qt signals.
