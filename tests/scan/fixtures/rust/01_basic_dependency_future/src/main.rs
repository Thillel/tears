// @tear: 0
#[path = "renamed.rs"]
mod aliased;
mod nested;
mod secret;

fn main() {
    let _ = aliased::value();
    let _ = nested::value();
    let _ = secret::value();
}
