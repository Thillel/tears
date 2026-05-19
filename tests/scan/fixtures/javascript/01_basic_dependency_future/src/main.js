// @tear: 0
import { secret } from "./secret.js";
import "./side_effect.js";
export { exported } from "./z_exported.js";

const required = require("./z_required.js");

export const value = secret();

export async function load() {
  return [required, await import("./z_dynamic.js")];
}
