// @tear: 0
package app

import app.alias.secret as aliasSecret
import app.secret.secret

fun render(): String {
  return secret() + aliasSecret()
}
