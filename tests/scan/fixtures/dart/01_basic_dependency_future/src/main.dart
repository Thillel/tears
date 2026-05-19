// @tear: 0
library fixture;

import './secret.dart';
export './z_exported.dart';
part 'z_part.dart';

String render() {
  return '$secret-$partSecret';
}
