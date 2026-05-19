// @tear: 0
using App.Secret;
using static App.StaticSecret.StaticSecretValue;

namespace App;

public static class MainProgram {
  public static string Run() {
    return SecretValue.Text + Text;
  }
}
