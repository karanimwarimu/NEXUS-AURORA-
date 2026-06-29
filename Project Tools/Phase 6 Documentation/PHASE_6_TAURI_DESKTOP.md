# NEXORA PHASE 6 IMPLEMENTATION FILE
# Complete Application Stack: Web App, Desktop App, CLI App & Deployment
# Version: 2.0.0 | Date: 2026-06-25
# Priority: P2 - DELIVERS THREE USER FACING APPLICATIONS

---

## 1. ARCHITECTURAL OVERVIEW & WORKFLOW

### 1.1 Core Philosophy: Multiple Interfaces, One Backend

Phase 6 completes the Nexora application ecosystem by delivering **three user-facing applications**, all powered by the same core backend (Phases 2-5). Users can choose their preferred interface:

| Application | Tech Stack | Best For | User Profile |
|-------------|-----------|----------|--------------|
| **Web Application** | Streamlit (from Phase 5) + FastAPI backend | Non-technical users, team dashboards | Business analysts, managers |
| **Desktop Application** | Tauri (Rust + React/TypeScript) + bundled Python | Power users, offline-first | Developers, researchers |
| **CLI Application** | Python argparse (from Phase 4) | Quick automation, scripts, CI/CD | Engineers, DevOps |

All three share the same:
- Scrapy-based crawling engine
- Redis/Celery distributed queue (optional)
- Markdown/AI/Parquet pipelines
- API authentication and rate limiting

### 1.2 Why Three Applications?

| Need | Solution | Competitor Comparison |
|------|----------|----------------------|
| "I just want to crawl a website, no code" | **Web Dashboard** on localhost:8501 | Firecrawl: missing self-hosted UI |
| "I need a native app on my desktop" | **Tauri Desktop** (Windows/macOS/Linux) | Apify: web-only, no desktop app |
| "I want to run this in a script or CI" | **nexora CLI** (`pip install`) | Scrapy: CLI only, no API. Firecrawl: API only, no local CLI |

### 1.3 Deployment Options

| Method | Complexity | Best For | Setup Time |
|--------|-----------|----------|------------|
| `pip install nexora` | Minimal | Individuals, quick testing | 2 minutes |
| Docker single container | Low | Teams, single-server | 5 minutes |
| Docker Compose (API + Redis + Worker + Dashboard) | Medium | Production, multi-worker | 10 minutes |
| Kubernetes | High | Enterprise, auto-scaling | 30 minutes |
| **PyInstaller bundle** (Desktop) | Medium | Offline desktop users | 15 minutes to build |

---

## 2. TECHNICAL REQUIREMENTS & DEPENDENCIES

### 2.1 Desktop Application Prerequisites

```bash
# Rust toolchain (required for Tauri)
# Download from: https://rustup.rs
rustup target add x86_64-pc-windows-msvc
rustup target add x86_64-apple-darwin
rustup target add x86_64-unknown-linux-gnu

# Node.js (for React frontend)
# Download from: https://nodejs.org (v20+ recommended)

# Tauri CLI
cargo install tauri-cli --version "^2"

# WebView2 Runtime (Windows only)
# Automatically installed on Windows 11+
# For Windows 10: https://developer.microsoft.com/microsoft-edge/webview2

# Build tools for Python bundle
pip install pyinstaller==6.6.0
```

### 2.2 Tauri Project Structure

```
nexora-desktop/
├── src-tauri/              # Rust backend
│   ├── Cargo.toml          # Rust dependencies
│   ├── tauri.conf.json     # Tauri configuration
│   ├── capabilities/
│   │   └── default.json    # Permission capabilities
│   ├── src/
│   │   ├── main.rs         # Entry point
│   │   ├── lib.rs          # Command handlers
│   │   └── python.rs       # Python process management
│   └── icons/
│       ├── icon.png
│       ├── icon.ico
│       └── icon.icns
├── src/                    # Frontend (React + TypeScript)
│   ├── main.tsx
│   ├── App.tsx
│   ├── App.css
│   ├── components/
│   │   ├── CrawlForm.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── ResultsTable.tsx
│   │   ├── MarkdownPreview.tsx
│   │   └── SettingsPanel.tsx
│   └── api/
│       ├── tauri.ts        # Tauri invoke wrappers
│       └── rest.ts         # Direct API calls (for server mode)
├── nexora-backend/         # Bundled Python backend
│   ├── main.py             # Entry point for embedded mode
│   ├── requirements.txt
│   └── nexora.spec         # PyInstaller spec
├── scripts/
│   ├── build-all.sh        # Full build script
│   └── build-windows.ps1   # Windows build script
├── package.json
├── vite.config.ts
├── tsconfig.json
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

# Web Application
NEXORA_DASHBOARD_PORT=8501
NEXORA_DASHBOARD_THEME=dark

# CLI Application
NEXORA_CLI_DEFAULT_OUTPUT=./nexora_output
NEXORA_CLI_DEFAULT_FORMAT=json
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
npm install @tauri-apps/plugin-shell @tauri-apps/plugin-dialog
npm install @radix-ui/react-progress @radix-ui/react-select
npm install @radix-ui/react-tabs @radix-ui/react-dialog
npm install lucide-react
npm install react-markdown remark-gfm
npm install tailwindcss @tailwindcss/vite
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
        "decorations": true,
        "theme": "Dark"
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://localhost:*; img-src 'self' data: https:; script-src 'self'; style-src 'self' 'unsafe-inline'"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis", "dmg", "appimage", "deb"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/icon.ico",
      "icons/icon.png"
    ],
    "windows": {
      "wix": {
        "language": "en-US",
        "template": "default"
      },
      "nsis": {
        "installMode": "currentUser"
      }
    },
    "macOS": {
      "minimumSystemVersion": "10.15",
      "entitlements": null
    },
    "linux": {
      "deb": {
        "depends": []
      },
      "appimage": {
        "bundleMediaFramework": false
      }
    }
  }
}
```

### Step 3: Build Rust Command Handlers

**File**: `src-tauri/src/lib.rs` (Updated)

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

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct CrawlRequest {
    pub url: String,
    pub strategy: String,
    pub max_pages: u32,
    pub output_format: String,
    pub crawl_name: Option<String>,
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
    pub current_url: Option<String>,
    pub error: Option<String>,
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
    let mut args = vec![
        backend_script.to_str().unwrap().to_string(),
        "crawl".to_string(),
        format!("--url={}", request.url),
        format!("--strategy={}", request.strategy),
        format!("--max-pages={}", request.max_pages),
        format!("--output-format={}", request.output_format),
        format!("--job-id={}", job_id),
        format!("--data-dir={}", get_data_dir(&app_handle)?.to_str().unwrap()),
    ];
    
    if let Some(name) = request.crawl_name {
        args.push(format!("--crawl-name={}", name));
    }
    
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
            current_url: None,
            error: None,
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

/// Get list of previous crawls
#[tauri::command]
pub async fn list_crawls(app_handle: tauri::AppHandle) -> Result<Vec<JobStatus>, String> {
    let data_dir = get_data_dir(&app_handle)?;
    let jobs_dir = data_dir.join("jobs");
    
    if !jobs_dir.exists() {
        return Ok(Vec::new());
    }
    
    let mut crawls = Vec::new();
    let mut entries: Vec<_> = std::fs::read_dir(&jobs_dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .collect();
    
    entries.sort_by_key(|e| e.metadata().ok().and_then(|m| m.created().ok()));
    entries.reverse();
    
    for entry in entries.iter().take(20) {
        let status_file = entry.path().join("status.json");
        if status_file.exists() {
            let content = std::fs::read_to_string(&status_file)
                .map_err(|e| e.to_string())?;
            if let Ok(status) = serde_json::from_str::<JobStatus>(&content) {
                crawls.push(status);
            }
        }
    }
    
    Ok(crawls)
}

/// Check if Python backend is available
#[tauri::command]
pub async fn check_backend(app_handle: tauri::AppHandle) -> Result<bool, String> {
    let python_exe = get_python_executable(&app_handle)?;
    Ok(python_exe.exists())
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
import { Play, Stop, FolderOpen, History } from 'lucide-react';

interface CrawlRequest {
  url: string;
  strategy: string;
  max_pages: number;
  output_format: string;
  crawl_name?: string;
}

interface CrawlResponse {
  job_id: string;
  status: string;
  message: string;
}

export const CrawlForm: React.FC = () => {
  const [url, setUrl] = useState('');
  const [strategy, setStrategy] = useState('whole-website');
  const [maxPages, setMaxPages] = useState(100);
  const [outputFormat, setOutputFormat] = useState('json');
  const [crawlName, setCrawlName] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);

  const handleStart = async () => {
    try {
      setIsRunning(true);
      setMessage('Starting crawl...');
      
      const response = await invoke<CrawlResponse>('start_crawl', {
        request: {
          url,
          strategy,
          max_pages: maxPages,
          output_format: outputFormat,
          crawl_name: crawlName || null,
        } as CrawlRequest,
      });
      
      setJobId(response.job_id);
      setMessage(`✅ Crawl started: ${response.job_id}`);
    } catch (error) {
      setMessage(`❌ Error: ${error}`);
      setIsRunning(false);
    }
  };

  const handleStop = async () => {
    try {
      await invoke('stop_crawl');
      setIsRunning(false);
      setMessage('⏹️ Crawl stopped');
    } catch (error) {
      setMessage(`❌ Error: ${error}`);
    }
  };

  const handleOpenDir = async () => {
    await invoke('open_output_dir');
  };

  return (
    <div className="crawl-form p-6 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">🕷️ Nexora Web Crawler</h2>
      
      <div className="space-y-4">
        {/* Crawl Name */}
        <div>
          <label className="block text-sm font-medium mb-1">Crawl Name (optional)</label>
          <input
            type="text"
            value={crawlName}
            onChange={(e) => setCrawlName(e.target.value)}
            placeholder="My Crawl"
            disabled={isRunning}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>

        {/* URL */}
        <div>
          <label className="block text-sm font-medium mb-1">Target URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            disabled={isRunning}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>

        {/* Strategy, Max Pages, Output Format */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={isRunning}
              className="w-full px-3 py-2 border rounded-md"
            >
              <option value="single-page">Single Page</option>
              <option value="linked-pages">Linked Pages</option>
              <option value="whole-website">Whole Website</option>
              <option value="everything">Everything</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Max Pages</label>
            <input
              type="number"
              value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
              min="1"
              max="10000"
              disabled={isRunning}
              className="w-full px-3 py-2 border rounded-md"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Output Format</label>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              disabled={isRunning}
              className="w-full px-3 py-2 border rounded-md"
            >
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
              <option value="parquet">Parquet</option>
              <option value="markdown">Markdown</option>
            </select>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 pt-4">
          <button
            onClick={handleStart}
            disabled={isRunning || !url}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            <Play size={16} /> Start Crawl
          </button>

          <button
            onClick={handleStop}
            disabled={!isRunning}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
          >
            <Stop size={16} /> Stop
          </button>

          <button
            onClick={handleOpenDir}
            className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
          >
            <FolderOpen size={16} /> Open Output
          </button>
        </div>

        {/* Status Message */}
        {message && (
          <div className="mt-4 p-3 bg-gray-100 rounded-md text-sm">
            {message}
          </div>
        )}

        {/* Progress Bar */}
        {jobId && isRunning && (
          <ProgressBar jobId={jobId} />
        )}
      </div>
    </div>
  );
};

// Inline ProgressBar component
const ProgressBar: React.FC<{ jobId: string }> = ({ jobId }) => {
  const [progress, setProgress] = useState(0);
  const [pages, setPages] = useState(0);

  React.useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const status: any = await invoke('get_job_status', { jobId });
        setProgress(status.progress || 0);
        setPages(status.pages_crawled || 0);
        
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(interval);
        }
      } catch (error) {
        console.error('Failed to get status:', error);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [jobId]);

  return (
    <div className="mt-4">
      <div className="flex justify-between text-sm mb-1">
        <span>Progress</span>
        <span>{pages} pages crawled</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 mt-1">{progress.toFixed(1)}%</span>
    </div>
  );
};

export default CrawlForm;
```

### Step 5: Python Backend Entry Point (Embedded Mode)

**File**: `nexora-backend/main.py` (Updated for Desktop)

```python
"""
Nexora Desktop Backend - Embedded Mode Entry Point
Called by Tauri Rust core as a sidecar process.
Supports crawl, status, and history commands.
"""

import argparse
import json
import os
import sys
import time
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


def crawl_command(args):
    """Execute a crawl job."""
    data_dir = Path(args.data_dir)
    output_dir = data_dir / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    
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
        
        # Configure output
        feed_uri = str(output_dir / f"{args.job_id}.{args.output_format}")
        settings.set('FEED_FORMAT', args.output_format)
        settings.set('FEED_URI', feed_uri)
        
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
            pages_crawled=args.max_pages,
        )
        
        print(f'Crawl complete: {feed_uri}')
        
    except Exception as exc:
        write_status(
            args.job_id, args.data_dir,
            status='failed',
            error=str(exc),
        )
        print(f'Crawl failed: {exc}', file=sys.stderr)
        raise


def status_command(args):
    """Get status of a job."""
    data_dir = Path(args.data_dir)
    status_file = data_dir / 'jobs' / args.job_id / 'status.json'
    
    if status_file.exists():
        print(status_file.read_text())
    else:
        print(json.dumps({
            'job_id': args.job_id,
            'status': 'not_found',
        }))


def main():
    parser = argparse.ArgumentParser(description='Nexora Desktop Backend')
    parser.add_argument('--data-dir', default=str(Path.cwd() / 'nexora_data'))
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Crawl command
    crawl_parser = subparsers.add_parser('crawl', help='Run a crawl')
    crawl_parser.add_argument('--url', required=True)
    crawl_parser.add_argument('--strategy', default='whole-website')
    crawl_parser.add_argument('--max-pages', type=int, default=100)
    crawl_parser.add_argument('--output-format', default='json')
    crawl_parser.add_argument('--job-id', required=True)
    crawl_parser.add_argument('--crawl-name', default='')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check job status')
    status_parser.add_argument('--job-id', required=True)
    
    args = parser.parse_args()
    
    if args.command == 'crawl':
        crawl_command(args)
    elif args.command == 'status':
        status_command(args)


if __name__ == '__main__':
    main()
```

### Step 6: PyInstaller Spec for Bundling Python

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
        'scrapy.spiders',
        'scrapy.crawler',
        'trafilatura',
        'pyarrow',
        'litellm',
        'httpx',
        'aiosqlite',
        'pandas',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'notebook',
        'jupyter',
    ],
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
    console=False,  # No console window for desktop app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

### Step 7: Build Scripts

**File**: `scripts/build-all.sh`

```bash
#!/bin/bash
set -e

echo '🔨 Building Nexora Desktop...'
echo ''

# 1. Build Python backend with PyInstaller
echo '1/4 Building Python backend...'
cd nexora-backend
python -m PyInstaller nexora.spec --clean --noconfirm
cd ..

# 2. Copy Python binary to Tauri resources
echo '2/4 Copying backend to Tauri resources...'
mkdir -p src-tauri/resources
cp nexora-backend/dist/nexora-backend src-tauri/resources/
cp -r nexora-backend/dist/nexora-backend/_internal src-tauri/resources/ || true

# 3. Build frontend
echo '3/4 Building frontend...'
npm install
npm run build

# 4. Build Tauri app
echo '4/4 Building Tauri app...'
cargo tauri build

echo ''
echo '✅ Build complete!'
echo 'Output: src-tauri/target/release/bundle/'
ls -la src-tauri/target/release/bundle/
```

**File**: `scripts/build-windows.ps1`

```powershell
# Build script for Windows
Write-Host "🔨 Building Nexora Desktop for Windows..." -ForegroundColor Cyan

# 1. Build Python backend
Write-Host "1/4 Building Python backend..."
Set-Location nexora-backend
python -m PyInstaller nexora.spec --clean --noconfirm
Set-Location ..

# 2. Copy to resources
Write-Host "2/4 Copying backend..."
New-Item -ItemType Directory -Force -Path src-tauri/resources
Copy-Item -Recurse -Force nexora-backend/dist/nexora-backend/* src-tauri/resources/

# 3. Build frontend
Write-Host "3/4 Building frontend..."
npm install
npm run build

# 4. Build Tauri (Windows MSI + NSIS)
Write-Host "4/4 Building Tauri app..."
cargo tauri build

Write-Host "✅ Build complete!" -ForegroundColor Green
```

### Step 8: Tauri Permissions

**File**: `src-tauri/capabilities/default.json`

```json
{
  "identifier": "default",
  "description": "Default capabilities for Nexora Desktop",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "shell:allow-open",
    "dialog:default",
    "dialog:allow-open",
    "dialog:allow-save",
    {
      "identifier": "fs:allow-read",
      "allow": [{ "path": "$APPDATA/**" }, { "path": "$RESOURCE/**" }]
    },
    {
      "identifier": "fs:allow-write",
      "allow": [{ "path": "$APPDATA/**" }]
    }
  ]
}
```

### Step 9: Web Application Refinement (from Phase 5)

The Streamlit dashboard from Phase 5 is the web application. Add these additional pages:

**File**: `nexora_crawler/dashboard/pages/1_Crawl.py` (NEW)

```python
"""
Crawl Page - Web Application
Advanced crawl submission with configuration options.
"""

import streamlit as st
import httpx
import os

API_BASE_URL = os.getenv('NEXORA_API_URL', 'http://localhost:8000')

st.set_page_config(page_title="New Crawl", page_icon="🔍", layout="wide")
st.markdown("# 🔍 New Crawl Job")

with st.form("advanced_crawl"):
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.text_input("URL", placeholder="https://example.com", key="crawl_url")
        st.text_area("Additional URLs (one per line)", height=100, key="additional_urls",
                     help="For batch crawling")
    
    with col2:
        st.selectbox("Strategy", ["single-page", "linked-pages", "whole-website", "everything"], 
                    index=2, key="crawl_strategy")
        st.number_input("Max Pages", min_value=1, max_value=100000, value=100, key="crawl_max_pages")
        st.selectbox("Output Format", ["json", "csv", "markdown", "parquet"], key="crawl_format")
    
    col3, col4 = st.columns(2)
    with col3:
        st.checkbox("Use Playwright (JS rendering)", value=False, key="use_playwright")
        st.checkbox("AI Enrichment", value=False, key="use_ai")
    with col4:
        st.checkbox("Proxy Rotation", value=False, key="use_proxy")
        st.checkbox("Capture Screenshots", value=False, key="use_screenshots")
    
    st.markdown("---")
    submitted = st.form_submit_button("🚀 Start Crawl", type="primary", use_container_width=True)
    
    if submitted:
        with st.spinner("Submitting crawl..."):
            try:
                response = httpx.post(
                    f"{API_BASE_URL}/crawl/start",
                    json={
                        "url": st.session_state.crawl_url,
                        "strategy": st.session_state.crawl_strategy,
                        "max_pages": st.session_state.crawl_max_pages,
                        "output_format": st.session_state.crawl_format,
                        "playwright": st.session_state.use_playwright,
                    },
                    timeout=30,
                )
                if response.status_code == 200:
                    result = response.json()
                    st.success(f"✅ Job submitted: {result['job_id']}")
                    st.info(f"View status at: {API_BASE_URL}/crawl/status/{result['job_id']}")
                else:
                    st.error(f"❌ Error: {response.text}")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")
```

**File**: `nexora_crawler/dashboard/pages/2_Results.py` (NEW)

```python
"""
Results Page - Web Application
View and download crawl results.
"""

import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Results", page_icon="📊", layout="wide")
st.markdown("# 📊 Crawl Results")

# In production, fetch from API
st.info("Connect to the API server to view results")

tab1, tab2, tab3 = st.tabs(["Table View", "JSON View", "Download"])

with tab1:
    st.dataframe(pd.DataFrame(), use_container_width=True)

with tab2:
    st.code("{}", language="json")

with tab3:
    st.download_button("Download JSON", data="{}", file_name="results.json")
    st.download_button("Download CSV", data="", file_name="results.csv")
```

### Step 10: CLI Application Refinement (from Phase 4)

The CLI from Phase 4 is already complete. Add this entry point for `pip install`:

**File**: `setup.py` (NEW - For PyPI packaging)

```python
"""
Nexora - Python Web Crawler
Packaged for pip install.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="nexora-crawler",
    version="2.0.0",
    author="Nexora Team",
    description="Industrial-grade web crawler with AI enrichment, REST API, and desktop app",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nexora/crawler",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
    install_requires=[
        "scrapy>=2.11",
        "playwright>=1.44",
        "trafilatura>=1.12",
        "litellm>=1.40",
        "pyarrow>=16.1",
        "fastapi>=0.111",
        "uvicorn>=0.29",
        "PyJWT>=2.8",
        "httpx>=0.27",
        "beautifulsoup4>=4.12",
        "lxml>=5.2",
    ],
    extras_require={
        "ai": ["ollama", "chromadb"],
        "api": ["redis", "celery", "slowapi"],
        "dashboard": ["streamlit", "pandas", "plotly"],
        "all": ["redis", "celery", "streamlit", "pandas", "plotly", "chromadb", "aiosqlite"],
    },
    entry_points={
        "console_scripts": [
            "nexora=nexora_crawler.cli.main:main",
        ],
    },
)
```

---

## 4. PRODUCTION CODE BLUEPRINT

### 4.1 Quick Start Script (All-in-One)

```bash
#!/bin/bash
# quick-start.sh - One command to run everything
set -e

echo "🚀 Nexora Quick Start"
echo "====================="

# Check if running in Docker
if [ -f /proc/1/cgroup ] && grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "Running in Docker container"
    exec uvicorn nexora_crawler.api.server:app --host 0.0.0.0 --port 8000
fi

case "${1:-help}" in
    api)
        echo "Starting API server..."
        uvicorn nexora_crawler.api.server:app --host 0.0.0.0 --port 8000 --reload
        ;;
    dashboard)
        echo "Starting Web Dashboard..."
        streamlit run nexora_crawler/dashboard/app.py --server.port=8501
        ;;
    worker)
        echo "Starting Celery worker..."
        celery -A nexora_crawler.celery_app worker --loglevel=info --concurrency=4
        ;;
    desktop)
        echo "Starting Tauri Desktop app..."
        cd nexora-desktop && npm run tauri dev
        ;;
    all)
        echo "Starting all services..."
        docker-compose up -d
        echo "API: http://localhost:8000"
        echo "Dashboard: http://localhost:8501"
        echo "Flower: http://localhost:5555"
        ;;
    *)
        echo "Usage: ./quick-start.sh [api|dashboard|worker|desktop|all]"
        echo ""
        echo "Quick crawl (no server needed):"
        echo "  nexora https://example.com"
        echo ""
        echo "Start services:"
        echo "  ./quick-start.sh api      # REST API on :8000"
        echo "  ./quick-start.sh dashboard # Web UI on :8501"
        echo "  ./quick-start.sh all      # Everything via Docker"
        ;;
esac
```

### 4.2 Docker Deployment Matrix

```yaml
# docker-compose.minimal.yml - Just the API + SQLite
version: '3.8'

services:
  api:
    build: .
    ports:
      - '8000:8000'
    volumes:
      - ./data:/data
    environment:
      - NEXORA_DATABASE_URL=sqlite:///./data/nexora.db
    command: uvicorn nexora_crawler.api.server:app --host 0.0.0.0 --port 8000
```

### 4.3 Application Comparison

| Feature | Web App (Streamlit) | Desktop App (Tauri) | CLI (nexora) |
|---------|-------------------|--------------------|-------------|
| **Installation** | `pip install streamlit` | Download installer | `pip install nexora` |
| **Startup** | `streamlit run app.py` | Double-click icon | `nexora https://...` |
| **UI** | Web browser | Native window | Terminal |
| **Offline** | Requires API | Fully offline | Fully offline |
| **Batch processing** | Via API | Via API | Native support |
| **Visual results** | Charts + tables | Markdown preview | File output |
| **Automation** | Manual | Manual | Scripts/CI |
| **Memory usage** | ~200 MB | ~500 MB | Variable |
| **Bundle size** | None (Python) | ~50 MB installer | ~50 MB (with deps) |

---

## 5. WHAT SUCCESS LOOKS LIKE

### 5.1 Test Matrix

| Test ID | Scenario | Expected | Pass Criteria |
|---------|----------|----------|---------------|
| P6-T01 | App launches | Window opens in < 2s | Tauri window visible, no crash |
| P6-T02 | URL input | Accepts valid URL | URL validation works, crawl starts |
| P6-T03 | Strategy selection | Dropdown works | All 4 strategies selectable |
| P6-T04 | Start crawl | Python backend spawns | Process visible, output created |
| P6-T05 | Progress bar | Updates in real-time | Progress increases, pages count updates |
| P6-T06 | Stop crawl | Process terminates | Python process killed, status = 'stopped' |
| P6-T07 | Open output | File manager opens | OS file manager opens at output dir |
| P6-T08 | Cross-platform | Builds on Windows/macOS/Linux | .msi, .dmg, .AppImage all generated |
| P6-T09 | Web dashboard loads | Streamlit UI on :8501 | Dashboard accessible in browser |
| P6-T10 | Dashboard submits crawl | Job created via UI | Job appears in recent jobs list |
| P6-T11 | CLI direct crawl | Output file created | File exists with crawled data |
| P6-T12 | CLI API mode | Communicates with API server | CLI submits via /crawl/start |
| P6-T13 | pip install | Package installs cleanly | `pip install nexora-crawler` succeeds |
| P6-T14 | Docker Compose | All services start | API, Redis, Worker healthy |
| P6-T15 | History view | Shows previous crawls | Desktop app lists recent jobs |

### 5.2 Performance Benchmarks

| Metric | Target | Acceptable |
|--------|--------|------------|
| App launch time (desktop) | < 2 s | < 5 s |
| Window bundle size | < 20 MB | < 50 MB |
| Memory usage (desktop idle) | < 100 MB | < 200 MB |
| Memory usage (desktop crawling) | < 1 GB | < 2 GB |
| Dashboard load time | < 2 s | < 5 s |
| CLI startup time | < 1 s | < 3 s |
| Docker Compose startup | < 10 s | < 30 s |
| pip install time | < 60 s | < 120 s |

### 5.3 Definition of Done

- [ ] All 15 test cases pass
- [ ] Desktop app launches on Windows, macOS, and Linux
- [ ] URL input and strategy selection work in desktop app
- [ ] Crawl starts and stops via desktop UI buttons
- [ ] Progress bar updates in real-time
- [ ] Output directory opens via OS file manager
- [ ] Bundle size under 50 MB per platform (desktop)
- [ ] **Web dashboard accessible on port 8501**
- [ ] **Dashboard can submit crawl jobs**
- [ ] **CLI works standalone (direct crawl)**
- [ ] **CLI works with API server (API mode)**
- [ ] **pip install nexora-crawler works**
- [ ] **Docker Compose starts all services**
- [ ] **No memory leaks during extended use**
- [ ] **Phase 5 tests still pass (no regression)**

---

## 6. KNOWN LIMITATIONS

| Limitation | Mitigation | Phase |
|------------|-----------|-------|
| WebView2 required on Windows | Auto-installer or bundled runtime | P6 |
| macOS notarization required | Apple Developer account + notarization script | P6 |
| Linux AppImage permissions | Document chmod +x requirement | P6 |
| Python bundle is large (~50 MB) | Use PyOxidizer for smaller binaries | P7 |
| No auto-updater for desktop | Integrate Tauri updater plugin | P7 |
| Streamlit is single-user | Add authentication or use FastAPI-only | P6 |
| No mobile app | Flutter or React Native in future | P7 |

---

## 7. NEXT PHASE GATE

Phase 6 is complete when all tests pass and benchmarks are met.
Phase 7 entry criteria: Phase 6 merged, all three applications stable, installer packages generated for all platforms.