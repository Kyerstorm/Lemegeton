use std::env;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(bla_shield)");
    println!("cargo:rerun-if-env-changed=LEMEGETON_BLA_SHIELD");

    if env::var_os("LEMEGETON_BLA_SHIELD").is_some() {
        println!("cargo:rustc-cfg=bla_shield");
    }
}
