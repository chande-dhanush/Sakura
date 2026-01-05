#!/usr/bin/env node
/**
 * Sakura V10 - Unified Pre-Build Script
 * 
 * Called automatically by Tauri's beforeBuildCommand.
 * Builds the Python backend with PyInstaller and copies to sidecar location.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const BACKEND_DIR = path.join(ROOT, 'backend');
const SIDECAR_DIR = path.join(__dirname, 'src-tauri', 'binaries');

console.log('🔧 Sakura Pre-Build: Compiling backend...');

// Ensure sidecar directory exists
if (!fs.existsSync(SIDECAR_DIR)) {
    fs.mkdirSync(SIDECAR_DIR, { recursive: true });
}

// Determine Python path (prefer venv)
const venvPython = path.join(ROOT, 'PA', 'Scripts', 'python.exe');
const pythonCmd = fs.existsSync(venvPython) ? `"${venvPython}"` : 'python';

console.log(`   Using Python: ${pythonCmd}`);
console.log(`   Backend dir: ${BACKEND_DIR}`);

try {
    // Step 1: Ensure PyInstaller is installed
    console.log('   Installing PyInstaller (if needed)...');
    execSync(`${pythonCmd} -m pip install pyinstaller --quiet`, {
        cwd: BACKEND_DIR,
        stdio: 'inherit'
    });

    // Step 2: Build with PyInstaller
    console.log('   Running PyInstaller...');
    execSync(`${pythonCmd} -m PyInstaller backend.spec --clean --noconfirm`, {
        cwd: BACKEND_DIR,
        stdio: 'inherit'
    });

    // Step 3: Copy to sidecar location
    const builtExe = path.join(BACKEND_DIR, 'dist', 'sakura-backend.exe');
    if (!fs.existsSync(builtExe)) {
        console.error('❌ PyInstaller did not produce expected output');
        process.exit(1);
    }

    // Tauri expects: {name}-{target}.exe
    const target = 'x86_64-pc-windows-msvc';
    const sidecarExe = path.join(SIDECAR_DIR, `sakura-backend-${target}.exe`);

    fs.copyFileSync(builtExe, sidecarExe);
    console.log(`✅ Backend compiled: ${sidecarExe}`);

} catch (error) {
    console.error('❌ Backend build failed:', error.message);
    process.exit(1);
}
