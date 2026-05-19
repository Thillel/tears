// @tear: 0
#include "secret.h"
#include "support/config.h"
#include <stdio.h>

int main(void) {
  return secret() + config_value();
}
