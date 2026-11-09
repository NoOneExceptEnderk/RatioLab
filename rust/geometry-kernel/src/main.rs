// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
use std::io::{self, BufRead};
fn main() {
    for line in io::stdin().lock().lines() {
        match line {
            Ok(s) => println!("{}", ratiolab_geometry::dispatch(&s)),
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
    }
}
