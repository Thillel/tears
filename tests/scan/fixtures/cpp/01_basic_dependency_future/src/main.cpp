// @tear: 0
#include "secret.hpp"
#include "support/config.hpp"
#include <vector>

int main() {
  return secret() + config_value();
}
