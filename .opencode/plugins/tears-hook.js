// @tear: 1
export const TearsHook = async ({ $, directory, worktree }) => {
  return {
    "tool.execute.after": async (input, output) => {
      const cwd = worktree || directory || "."
      const filePaths = new Set()

      if (input.tool === "edit" || input.tool === "write") {
        const filePath = input.args?.filePath || output?.args?.filePath || ""
        if (filePath) filePaths.add(filePath)
      } else if (input.tool === "apply_patch") {
        const text = input.args?.patchText || output?.args?.patchText || ""
        const patchPathPattern = /^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm
        for (const match of text.matchAll(patchPathPattern)) {
          filePaths.add(match[1])
        }
      }

      if (filePaths.size === 0) {
        return
      }

      for (const filePath of filePaths) {
        await $`uv run python -m tears.hook ${filePath}`.cwd(cwd)
      }
    },
  }
}
