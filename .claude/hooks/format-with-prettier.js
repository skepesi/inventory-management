#!/usr/bin/env node
// PostToolUse hook: formats a file with Prettier after Claude edits or writes it.
// Claude Code passes the edited file's path as JSON on stdin, not in an environment variable.
const { spawnSync } = require('node:child_process')
const path = require('node:path')

let input = ''
process.stdin.on('data', (chunk) => (input += chunk))
process.stdin.on('end', () => {
  const filePath = JSON.parse(input).tool_input?.file_path
  if (!filePath) return

  // Only format frontend files, because Prettier and its config are installed in client/.
  const projectDir = process.env.CLAUDE_PROJECT_DIR || path.resolve(__dirname, '..', '..')
  const clientDir = path.join(projectDir, 'client')
  const relative = path.relative(clientDir, path.resolve(filePath))
  if (relative.startsWith('..') || path.isAbsolute(relative)) return

  const prettier = path.join(clientDir, 'node_modules', 'prettier', 'bin', 'prettier.cjs')
  const result = spawnSync(process.execPath, [prettier, '--write', '--ignore-unknown', filePath], {
    cwd: clientDir,
    encoding: 'utf8'
  })

  // Report failures without blocking the edit, which has already been applied.
  if (result.status !== 0) {
    console.error(`Prettier failed for ${filePath}: ${result.stderr || result.error}`)
    process.exit(1)
  }
})
