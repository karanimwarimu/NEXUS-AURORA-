# NEXORA PHASE 6 IMPLEMENTATION FILE
# Tauri Desktop GUI & Cross-Platform Packaging
# Version: 1.0.0 | Date: 2026-06-24
# Priority: P2 - USER-FACING INTERFACE

---

## 1. ARCHITECTURAL OVERVIEW & WORKFLOW

### 1.1 Core Philosophy: Web Tech Frontend, Rust Core, Python Backend

Tauri is the optimal choice for Nexora's desktop GUI because it provides a modern web-based UI (React/Vue/Svelte) with a Rust core that can embed and communicate with our Python backend. This gives us native performance, tiny bundle sizes (~600 KB vs Electron's ~150 MB), and full access to OS APIs.

### 1.2 Why Tauri vs Electron

| Metric | Electron | Tauri |
|--------|----------|-------|
| Bundle Size | 150+ MB | 3-15 MB |
| RAM Usage | 300-500 MB | 50-150 MB |
| Startup Time | 3-5 s | < 1 s |
| Security | V8 sandbox | Rust memory safety |
| Native APIs | Limited | Full OS access |
| Python Integration | Node-ffi | Direct process spawn |

---

## 2. TECHNICAL REQUIREMENTS & DEPENDENCIES

### 2.1 Prerequisites

```bash
# Rust toolchain (required for Tauri)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup target add x86_64-pc-windows-msvc
rustup target add x86_64-apple-darwin
rustup target add x86_64-unknown-linux-gnu

# Node.js (for frontend build)
# Download from https://nodejs.org (v20+ recommended)

# Tauri CLI
cargo install tauri-cli
# OR: npm install -g @tauri-apps/cli

# WebView2 Runtime (Windows only)
# Automatically installed on Windows 11+
# For Windows 10: https://developer.microsoft.com/microsoft-edge/webview2
```

### 2.2 Tauri Project Structure

```
nexora-desktop/
├── src-tauri/              # Rust backend
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── src/
│   │   ├── main.rs         # Entry point
│   │   ├── lib.rs          # Commands
│   │   └── python.rs       # Python process management
│   └── icons/
├── src/                    # Frontend (React/Vue)
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── CrawlForm.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── ResultsTable.tsx
│   │   └── MarkdownPreview.tsx
│   └── api/
│       └── tauri.ts        # Tauri command wrappers
├── nexora-backend/         # Bundled Python backend
│   ├── main.py             # Entry point for embedded mode
│   └── requirements.txt
├── package.json
├── vite.config.ts
└── index.html
```

### 2.3 Environment Variables

```bash
# Tauri Development
TAURI_DEV_PORT=1420
TAURI_BACKEND_PATH=./nexora-backend

# Python Backend (embedded mode)
NEXORA_EMBEDDED=true
NEXORA_DATA_DIR=${APP_DATA_DIR}
NEXORA_LOG_LEVEL=info
```

---

## 3. STEP-BY-STEP IMPLEMENTATION BLUEPRINT

### Step 1: Initialize Tauri Project

```bash
# Create project directory
mkdir nexora-desktop && cd nexora-desktop

# Initialize with React + TypeScript
npm create vite@latest . -- --template react-ts

# Add Tauri
npm install @tauri-apps/api @tauri-apps/cli
npx tauri init

# Install UI dependencies
npm install @radix-ui/react-progress @radix-ui/react-select
npm install @radix-ui/react-tabs @radix-ui/react-dialog
npm install lucide-react tailwindcss
npm install react-markdown remark-gfm
```

### Step 2: Configure Tauri (tauri.conf.json)

```json
{
  "productName": "Nexora Crawler",
  "version": "2.0.0",
  "identifier": "com.nexora.crawler",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:1420",
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build"
  },
  "app": {
    "windows": [
      {
        "title": "Nexora Crawler",
        "width": 1280,
        "height": 800,
        "minWidth": 800,
        "minHeight": 600,
        "center": true,
        "resizable": true,
        "fullscreen": false,
        "decorations": true,
        "transparent": false,
        "alwaysOnTop": false,
        "contentProtected": false,
        "skipTaskbar": false,
        "theme": "Dark"
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://localhost:*; img-src 'self' data: https:; script-src 'self'; style-src 'self' 'unsafe-inline'"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "dmg", "appimage", "nsis"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/icon.ico"
    ],
    "windows": {
      "certificateThumbprint": null,
      "digestAlgorithm": "sha256",
      "timestampUrl": ""
    },
    "macOS": {
      "frameworks": [],
      "minimumSystemVersion": "10.13",
      "license": ""
    },
    "linux": {
      "appimage": {
        "bundleMediaFramework": false
      }
    }
  }
}
```

### Step 3: Build Rust Command Handlers

**File**: `src-tauri/src/lib.rs`

```rust
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::path::PathBuf;
use tauri::{Manager, State};
use serde::{Deserialize, Serialize};

// Global state for Python process
pub struct PythonProcessState {
    pub process: Mutex<Option<std::process::Child>>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CrawlRequest {
    pub url: String,
    pub strategy: String,
    pub max_pages: u32,
    pub output_format: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct CrawlResponse {
    pub job_id: String,
    pub status: String,
    pub message: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct JobStatus {
    pub job_id: String,
    pub status: String,
    pub progress: f32,
    pub pages_crawled: u32,
    pub total_pages: u32,
}

/// Start a crawl job by spawning the Python backend
#[tauri::command]
pub async fn start_crawl(
    request: CrawlRequest,
    app_handle: tauri::AppHandle,
    state: State<'_, PythonProcessState>,
) -> Result<CrawlResponse, String> {
    let job_id = uuid::Uuid::new_v4().to_string();
    
    // Get the bundled Python executable path
    let python_exe = get_python_executable(&app_handle)?;
    let backend_script = get_backend_script(&app_handle)?;
    
    // Build command arguments
    let args = vec![
        backend_script.to_str().unwrap().to_string(),
        "crawl".to_string(),
        format!("--url={}", request.url),
        format!("--strategy={}", request.strategy),
        format!("--max-pages={}", request.max_pages),
        format!("--output-format={}", request.output_format),
        format!("--job-id={}", job_id),
        format!("--data-dir={}", get_data_dir(&app_handle)?.to_str().unwrap()),
    ];
    
    // Spawn Python process
    let mut child = Command::new(python_exe)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start Python backend: {}", e))?;
    
    // Store process handle
    let mut process_guard = state.process.lock().map_err(|e| e.to_string())?;
    *process_guard = Some(child);
    
    Ok(CrawlResponse {
        job_id,
        status: "started".to_string(),
        message: "Crawl job started successfully".to_string(),
    })
}

/// Get current job status from output files
#[tauri::command]
pub async fn get_job_status(
    job_id: String,
    app_handle: tauri::AppHandle,
) -> Result<JobStatus, String> {
    let data_dir = get_data_dir(&app_handle)?;
    let status_file = data_dir.join(format!("jobs/{}/status.json", job_id));
    
    if !status_file.exists() {
        return Ok(JobStatus {
            job_id,
            status: "unknown".to_string(),
            progress: 0.0,
            pages_crawled: 0,
            total_pages: 0,
        });
    }
    
    let content = std::fs::read_to_string(&status_file)
        .map_err(|e| format!("Failed to read status: {}", e))?;
    
    let status: JobStatus = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse status: {}", e))?;
    
    Ok(status)
}

/// Stop the current crawl job
#[tauri::command]
pub async fn stop_crawl(
    state: State<'_, PythonProcessState>,
) -> Result<String, String> {
    let mut process_guard = state.process.lock().map_err(|e| e.to_string())?;
    
    if let Some(ref mut child) = *process_guard {
        child.kill().map_err(|e| format!("Failed to stop: {}", e))?;
        *process_guard = None;
        Ok("Crawl stopped".to_string())
    } else {
        Ok("No active crawl".to_string())
    }
}

/// Open the output directory in file manager
#[tauri::command]
pub async fn open_output_dir(app_handle: tauri::AppHandle) -> Result<(), String> {
    let data_dir = get_data_dir(&app_handle)?;
    
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(data_dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(data_dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(data_dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    
    Ok(())
}

// --- Helper Functions ---

fn get_python_executable(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    // In production, use bundled Python sidecar
    let resource_dir = app_handle.path().resource_dir()
        .map_err(|e| e.to_string())?;
    
    let python_exe = resource_dir.join("python");
    if python_exe.exists() {
        return Ok(python_exe);
    }
    
    // Fallback to system Python (development)
    #[cfg(target_os = "windows")]
    {
        Ok(PathBuf::from("python.exe"))
    }
    #[cfg(not(target_os = "windows"))]
    {
        Ok(PathBuf::from("python3"))
    }
}

fn get_backend_script(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app_handle.path().resource_dir()
        .map_err(|e| e.to_string())?;
    Ok(resource_dir.join("nexora-backend/main.py"))
}

fn get_data_dir(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data = app_handle.path().app_data_dir()
        .map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&app_data).map_err(|e| e.to_string())?;
    Ok(app_data)
}
```

### Step 4: Build React Frontend Components

**File**: `src/components/CrawlForm.tsx`

```typescript
import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Play, Stop, Settings, FolderOpen } from 'lucide-react';

interface CrawlRequest {
  url: string;
  strategy: string;
  max_pages: number;
  output_format: string;
}

export const CrawlForm: React.FC = () => {
  const [url, setUrl] = useState('');
  const [strategy, setStrategy] = useState('whole-website');
  const [maxPages, setMaxPages] = useState(100);
  const [outputFormat, setOutputFormat] = useState('json');
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState('');

  const handleStart = async () => {
    try {
      setIsRunning(true);
      setMessage('Starting crawl...');
      
      const response = await invoke('start_crawl', {
        request: {
          url,
          strategy,
          max_pages: maxPages,
          output_format: outputFormat,
        } as CrawlRequest,
      });
      
      setMessage(`Crawl started: ${(response as any).job_id}`);
    } catch (error) {
      setMessage(`Error: ${error}`);
      setIsRunning(false);
    }
  };

  const handleStop = async () => {
    try {
      await invoke('stop_crawl');
      setIsRunning(false);
      setMessage('Crawl stopped');
    } catch (error) {
      setMessage(`Error: ${error}`);
    }
  };

  const handleOpenDir = async () => {
    await invoke('open_output_dir');
  };

  return (
    <div className='crawl-form'>
      <h2>Nexora Web Crawler</h2>
      
      <div className='form-group'>
        <label>Target URL</label>
        <input
          type='url'
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder='https://example.com'
          disabled={isRunning}
        />
      </div>

      <div className='form-row'>
        <div className='form-group'>
          <label>Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            disabled={isRunning}
          >
            <option value='single-page'>Single Page</option>
            <option value='linked-pages'>Linked Pages</option>
            <option value='whole-website'>Whole Website</option>
            <option value='everything'>Everything</option>
          </select>
        </div>

        <div className='form-group'>
          <label>Max Pages</label>
          <input
            type='number'
            value={maxPages}
            onChange={(e) => setMaxPages(Number(e.target.value))}
            min='1'
            max='10000'
            disabled={isRunning}
          />
        </div>

        <div className='form-group'>
          <label>Output Format</label>
          <select
            value={outputFormat}
            onChange={(e) => setOutputFormat(e.target.value)}
            disabled={isRunning}
          >
            <option value='json'>JSON</option>
            <option value='csv'>CSV</option>
            <option value='parquet'>Parquet</option>
            <option value='markdown'>Markdown</option>
          </select>
        </div>
      </div>

      <div className='button-group'>
        <button
          onClick={handleStart}
          disabled={isRunning || !url}
          className='btn-primary'
        >
          <Play size={16} /> Start Crawl
        </button>

        <button
          onClick={handleStop}
          disabled={!isRunning}
          className='btn-danger'
        >
          <Stop size={16} /> Stop
        </button>

        <button
          onClick={handleOpenDir}
          className='btn-secondary'
        >
          <FolderOpen size={16} /> Open Output
        </button>
      </div>

      {message && <div className='message'>{message}</div>}
    </div>
  );
};
```

**File**: `src/components/ProgressBar.tsx`

```typescript
import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface JobStatus {
  job_id: string;
  status: string;
  progress: number;
  pages_crawled: number;
  total_pages: number;
}

export const ProgressBar: React.FC<{ jobId: string }> = ({ jobId }) => {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const result = await invoke('get_job_status', { jobId });
        setStatus(result as JobStatus);
        
        if ((result as JobStatus).status === 'completed' ||
            (result as JobStatus).status === 'failed') {
          clearInterval(interval);
        }
      } catch (error) {
        console.error('Failed to get status:', error);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [jobId]);

  if (!status) return null;

  return (
    <div className='progress-container'>
      <div className='progress-header'>
        <span>Status: {status.status}</span>
        <span>{status.pages_crawled} / {status.total_pages} pages</span>
      </div>
      <div className='progress-bar'>
        <div
          className='progress-fill'
          style={{ width: `${status.progress}%` }}
        />
      </div>
      <div className='progress-percent'>{status.progress.toFixed(1)}%</div>
    </div>
  );
};
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Python Backend Entry Point (Embedded Mode)

**File**: `nexora-backend/main.py`

```python
"""
Nexora Desktop Backend - Embedded Mode Entry Point
Called by Tauri Rust core as a sidecar process.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add bundled packages to path
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    bundle_dir = Path(sys._MEIPASS)
else:
    bundle_dir = Path(__file__).parent

sys.path.insert(0, str(bundle_dir))


def write_status(job_id: str, data_dir: str, **kwargs):
    """Write job status to JSON file for Tauri to read."""
    status_dir = Path(data_dir) / 'jobs' / job_id
    status_dir.mkdir(parents=True, exist_ok=True)
    
    status_file = status_dir / 'status.json'
    status = {
        'job_id': job_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    status_file.write_text(json.dumps(status))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['crawl', 'status'])
    parser.add_argument('--url', required=True)
    parser.add_argument('--strategy', default='whole-website')
    parser.add_argument('--max-pages', type=int, default=100)
    parser.add_argument('--output-format', default='json')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args()
    
    if args.command == 'crawl':
        # Initialize status
        write_status(
            args.job_id, args.data_dir,
            status='running',
            progress=0.0,
            pages_crawled=0,
            total_pages=args.max_pages,
        )
        
        try:
            # Import and run Scrapy spider
            from scrapy.crawler import CrawlerProcess
            from scrapy.utils.project import get_project_settings
            
            settings = get_project_settings()
            settings.set('JOB_ID', args.job_id)
            settings.set('DATA_DIR', args.data_dir)
            
            process = CrawlerProcess(settings)
            process.crawl(
                'nexora',
                urls=args.url,
                strategy=args.strategy,
                max_pages=args.max_pages,
            )
            process.start()
            
            # Mark complete
            write_status(
                args.job_id, args.data_dir,
                status='completed',
                progress=100.0,
            )
            
        except Exception as exc:
            write_status(
                args.job_id, args.data_dir,
                status='failed',
                error=str(exc),
            )
            raise


if __name__ == '__main__':
    main()
```

### 4.2 PyInstaller Spec for Bundling Python

**File**: `nexora-backend/nexora.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../nexora_crawler', 'nexora_crawler'),
    ],
    hiddenimports=[
        'scrapy',
        'trafilatura',
        'pyarrow',
        'litellm',
        'celery',
        'redis',
        'httpx',
        'aiosqlite',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='nexora-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

### 4.3 Build Scripts

**File**: `scripts/build-all.sh`

```bash
#!/bin/bash
set -e

echo 'Building Nexora Desktop...'

# 1. Build Python backend with PyInstaller
echo '-> Building Python backend...'
cd nexora-backend
python -m PyInstaller nexora.spec --clean --noconfirm
cd ..

# 2. Copy Python binary to Tauri resources
echo '-> Copying backend to Tauri resources...'
mkdir -p src-tauri/resources
cp nexora-backend/dist/nexora-backend src-tauri/resources/
cp -r nexora-backend/dist/nexora-backend/_internal src-tauri/resources/ || true

# 3. Build Tauri frontend
echo '-> Building frontend...'
npm install
npm run build

# 4. Build Tauri app
echo '-> Building Tauri app...'
cargo tauri build

echo 'Build complete!'
echo 'Output: src-tauri/target/release/bundle/'
```

---

## 5. WHAT SUCCESS LOOKS LIKE

### 5.1 Test Matrix

| Test ID | Scenario | Expected | Pass Criteria |
|---------|----------|----------|---------------|
| P6-T01 | App launches | Window opens in < 2s | Tauri window visible, no crash |
| P6-T02 | URL input | Accepts valid URL | URL validation works, crawl starts |
| P6-T03 | Strategy selection | Dropdown works | All 4 strategies selectable |
| P6-T04 | Start crawl | Python backend spawns | Process visible in Task Manager, output created |
| P6-T05 | Progress bar | Updates in real-time | Progress increases, pages count updates |
| P6-T06 | Stop crawl | Process terminates | Python process killed, status = 'stopped' |
| P6-T07 | Open output | File manager opens | OS file manager opens at output dir |
| P6-T08 | Results table | Shows crawled pages | Table populated with URLs, titles, status |
| P6-T09 | Markdown preview | Renders clean Markdown | Markdown preview panel shows formatted text |
| P6-T10 | Cross-platform | Builds on Windows/macOS/Linux | .msi, .dmg, .AppImage all generated |

### 5.2 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| App launch time | < 2 s | < 5 s |
| Window bundle size | < 20 MB | < 50 MB |
| Memory usage (idle) | < 100 MB | < 200 MB |
| Memory usage (crawling) | < 1 GB | < 2 GB |
| UI responsiveness | 60 FPS | > 30 FPS |
| Status poll interval | 1 s | < 3 s |
| Cross-build time | < 10 min | < 30 min |

### 5.3 Definition of Done

- [ ] All 10 test cases pass
- [ ] App launches on Windows, macOS, and Linux
- [ ] URL input and strategy selection work correctly
- [ ] Crawl starts and stops via UI buttons
- [ ] Progress bar updates in real-time
- [ ] Results table shows crawled page data
- [ ] Markdown preview renders extracted content
- [ ] Output directory opens via OS file manager
- [ ] Bundle size under 50 MB per platform
- [ ] No memory leaks during extended use
- [ ] Phase 5 tests still pass (no regression)

---

## 6. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|------------|-----------|-------|
| WebView2 required on Windows | Auto-installer or bundled runtime | P6 |
| macOS notarization required | Apple Developer account + notarization script | P6 |
| Linux AppImage permissions | Document chmod +x requirement | P6 |
| Python bundle is large | Use PyOxidizer for smaller binaries | P7 |
| No auto-updater | Integrate Tauri updater plugin | P7 |

---

## 7. NEXT PHASE GATE

Phase 6 is complete when all tests pass and benchmarks are met.
Phase 7 entry criteria: Phase 6 merged, desktop app stable on all 3 platforms, installer packages generated.