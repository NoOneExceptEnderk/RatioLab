// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
//! Additive diagnostics through the kernel's existing String error channel.
//! Only this explicit envelope is decoded; legacy prose is never classified.
use serde_json::{Value, json};

pub fn constraint(id: &str, fields: &[&str], message: &str, remedy: &str) -> String {
    json!({"format":"ratiolab.diagnostic/1","code":"invalid_geometry",
        "kind":"geometry","constraint":id,"fields":fields,
        "message":message,"remedy":remedy})
    .to_string()
}

pub fn record(message: String) -> Value {
    if let Ok(value) = serde_json::from_str::<Value>(&message) {
        if value["format"] == "ratiolab.diagnostic/1" {
            return value;
        }
    }
    json!({"code":"geometry_error","message":message})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn transport_is_independent_of_prose() {
        let value = record(constraint(
            "test.constraint",
            &["a", "b"],
            "qualsiasi testo",
            "",
        ));
        assert_eq!(value["fields"], json!(["a", "b"]));
        assert_eq!(value["constraint"], "test.constraint");
        assert!(record("eccentric bore error".into())["fields"].is_null());
    }
}
