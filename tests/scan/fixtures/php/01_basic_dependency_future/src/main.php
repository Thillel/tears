<?php
// @tear: 0
require_once __DIR__ . "/secret.php";
include_once __DIR__ . "/nested/tool.php";

echo secret() . tool();
