// @tear: 0
package main

import (
	_ "example.com/tearsfixture/src/sideeffect"
	"example.com/tearsfixture/src/secret"
	aliassecret "example.com/tearsfixture/src/zalias"
	. "example.com/tearsfixture/src/zdot"
)

func main() {
	_ = secret.Value()
	_ = aliassecret.Value()
	_ = DotValue()
}
