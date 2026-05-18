// @tear: 0
import type { UserRecord } from "./types";

export function render(user: UserRecord): string {
  return user.name;
}
