// @tear: 3
export const TearsHook = async ({ $, directory, worktree }) => {
  return {
    "tool.execute.after": async (input, output) => {
      const cwd = worktree || directory || "."

      // Debug: write to log when any tool fires
      await $`echo "[tears] tool=${input.tool} at $(date)" >> /tmp/tears-hook.log`.cwd(cwd)

      let filePath = ""

      if (input.tool === "edit" || input.tool === "write") {
        filePath = input.args?.filePath || output?.args?.filePath || ""
      } else if (input.tool === "apply_patch") {
        const text = input.args?.patchText || output?.args?.patchText || ""
        const m = text.match(/^\*\*\* (?:Add File|Update File): (.+)$/m)
        if (m) filePath = m[1]
      }

      if (!filePath) {
        await $`echo "[tears] no filePath for tool=${input.tool}" >> /tmp/tears-hook.log`.cwd(cwd)
        return
      }
      await $`uv run python -m tears.hook ${filePath}`.cwd(cwd)
      await $`echo "[tears] hook ran for ${filePath}" >> /tmp/tears-hook.log`.cwd(cwd)
    },
  }
}
