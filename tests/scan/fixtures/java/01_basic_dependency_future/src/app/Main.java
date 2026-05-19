// @tear: 0
package app;

import app.secret.Secret;
import static app.staticsecret.StaticSecret.staticValue;

public final class Main {
  public String render() {
    return Secret.value() + staticValue();
  }
}
