import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

export const privateRoot = path.join(os.homedir(), '.codex/private/bizbase-round01');

export async function launch() {
  const executablePath = process.env.BIZBASE_TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  await fs.access(executablePath);
  return chromium.launch({ executablePath, headless: true });
}

export async function evidence(name, payload) {
  const directory = path.join(privateRoot, 'evidence');
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const file = path.join(directory, name);
  await fs.writeFile(file, JSON.stringify(payload, null, 2) + '\n', { mode: 0o600 });
  await fs.chmod(file, 0o600);
  return file;
}

export async function screenshot(page, name) {
  const directory = path.join(privateRoot, 'evidence');
  await fs.mkdir(directory, { recursive: true, mode: 0o700 });
  const file = path.join(directory, name);
  await page.screenshot({ path: file, fullPage: true });
  await fs.chmod(file, 0o600);
  return file;
}
