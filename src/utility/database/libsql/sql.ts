function quoteSql(value: string): string {
  return "'" + value.replaceAll("'", "''") + "'";
}

function splitSqlList(source: string): string[] {
  const output: string[] = [];
  let current = "";
  let quote = "";
  let depth = 0;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index] ?? "";
    if (quote) {
      current += char;
      if (char === quote) {
        if (source[index + 1] === quote) {
          current += source[index + 1];
          index += 1;
        } else {
          quote = "";
        }
      }
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      current += char;
    } else if (char === "(") {
      depth += 1;
      current += char;
    } else if (char === ")") {
      depth -= 1;
      current += char;
    } else if (char === "," && depth === 0) {
      output.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  if (current.trim()) output.push(current.trim());
  return output;
}

function literalArrayJson(values: string[]): string | null {
  const encoded: unknown[] = [];
  for (const raw of values) {
    const item = raw.replace(/::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|UUID|BOOLEAN)\b/gi, "").trim();
    if (/^NULL$/i.test(item)) encoded.push(null);
    else if (/^(?:TRUE|FALSE)$/i.test(item)) encoded.push(/^TRUE$/i.test(item));
    else if (/^-?\d+(?:\.\d+)?$/.test(item)) encoded.push(Number(item));
    else if (/^'(?:[^']|'')*'$/.test(item)) encoded.push(item.slice(1, -1).replaceAll("''", "'"));
    else return null;
  }
  return JSON.stringify(encoded);
}

function translateArrayExpressions(source: string, schema: boolean): string {
  const expression = /\bARRAY\s*\[/gi;
  let output = "";
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = expression.exec(source))) {
    const open = source.indexOf("[", match.index);
    let depth = 1;
    let quote = "";
    let close = -1;
    for (let index = open + 1; index < source.length; index += 1) {
      const char = source[index] ?? "";
      if (quote) {
        if (char === quote) {
          if (source[index + 1] === quote) index += 1;
          else quote = "";
        }
        continue;
      }
      if (char === "'" || char === '"') quote = char;
      else if (char === "[") depth += 1;
      else if (char === "]" && --depth === 0) {
        close = index;
        break;
      }
    }
    if (close < 0) break;
    const contents = source.slice(open + 1, close);
    let end = close + 1;
    const cast = source.slice(end).match(/^\s*::\s*(?:TEXT|INTEGER|BIGINT|SMALLINT|UUID)\s*\[\]/i);
    if (cast) end += cast[0].length;
    const entries = splitSqlList(contents);
    const literal = literalArrayJson(entries);
    const replacement = entries.length === 0
      ? "'[]'"
      : schema && literal !== null
        ? quoteSql(literal)
        : "json_array(" + contents.replace(/::\s*(?:TEXT|INTEGER|BIGINT|SMALLINT|UUID|BOOLEAN)\b/gi, "") + ")";
    output += source.slice(cursor, match.index) + replacement;
    cursor = end;
    expression.lastIndex = end;
  }
  return output + source.slice(cursor);
}

function regexToGlob(source: string): string {
  let pattern = source.trim();
  const anchoredStart = pattern.startsWith("^");
  const anchoredEnd = pattern.endsWith("$");
  if (anchoredStart) pattern = pattern.slice(1);
  if (anchoredEnd) pattern = pattern.slice(0, -1);

  pattern = pattern.replace(/\((?:\?:)?www\\\.\)\?/gi, "*");
  pattern = pattern.replace(/\((?:\?:)?[^()]*\|[^()]*\)/g, "*");
  pattern = pattern.replace(/\((?:\?:)?([^()]+)\)\?/g, "*");
  pattern = pattern.replace(/\\\./g, ".");
  pattern = pattern.replace(/\\\//g, "/");
  pattern = pattern.replace(/\\-/g, "-");
  pattern = pattern.replace(/\\d/g, "[0-9]");
  pattern = pattern.replace(/\\w/g, "[A-Za-z0-9_]");
  pattern = pattern.replace(/\\s/g, "?");
  pattern = pattern.replace(/(\[[^\]]+\])\+/g, "$1$1*");
  pattern = pattern.replace(/(\[[^\]]+\])\*/g, "$1*");
  pattern = pattern.replace(/\.\*/g, "*");
  pattern = pattern.replace(/\.\+/g, "?*");
  pattern = pattern.replace(/\./g, "?");
  pattern = pattern.replace(/\(/g, "").replace(/\)/g, "");
  pattern = pattern.replace(/\|/g, "*").replace(/\+/g, "*");
  if (!anchoredStart) pattern = "*" + pattern;
  if (!anchoredEnd) pattern += "*";
  return pattern.replace(/\*{2,}/g, "*");
}

function translateRegexOperators(sql: string): string {
  sql = sql.replace(
    /([A-Za-z_][A-Za-z0-9_.]*)\s+~\s*'\^\[a-f0-9\]\{40\}\$'/gi,
    (_match, column: string) => "(length(" + column + ") = 40 AND " + column + " NOT GLOB '*[^a-f0-9]*')",
  );
  sql = sql.replace(
    /([A-Za-z_][A-Za-z0-9_.]*)\s+~\s*'\^\[0-9\]\+\$'/gi,
    (_match, column: string) => "(length(" + column + ") > 0 AND " + column + " NOT GLOB '*[^0-9]*')",
  );
  return sql.replace(
    /([A-Za-z_][A-Za-z0-9_.]*)\s*(!~\*|~\*|!~|~)\s*'((?:[^']|'')*)'/gi,
    (_match, column: string, operator: string, rawPattern: string) => {
      const pattern = regexToGlob(rawPattern.replaceAll("''", "'"));
      const insensitive = operator.endsWith("*");
      const negative = operator.startsWith("!");
      const left = insensitive ? "LOWER(" + column + ")" : column;
      const right = quoteSql(insensitive ? pattern.toLowerCase() : pattern);
      return left + (negative ? " NOT GLOB " : " GLOB ") + right;
    },
  );
}

function removeUnsupportedCheckConstraints(source: string): string {
  let output = "";
  let cursor = 0;
  const check = /\bCHECK\s*\(/gi;
  let match: RegExpExecArray | null;
  while ((match = check.exec(source))) {
    const open = source.indexOf("(", match.index);
    let depth = 1;
    let quote = "";
    let close = -1;
    for (let index = open + 1; index < source.length; index += 1) {
      const char = source[index] ?? "";
      if (quote) {
        if (char === quote) {
          if (source[index + 1] === quote) index += 1;
          else quote = "";
        }
        continue;
      }
      if (char === "'" || char === '"') quote = char;
      else if (char === "(") depth += 1;
      else if (char === ")" && --depth === 0) {
        close = index;
        break;
      }
    }
    if (close < 0) break;
    const clause = source.slice(match.index, close + 1);
    if (/(?:<@|@>|\bcardinality\s*\()/i.test(clause)) {
      const prefix = source.slice(cursor, match.index).replace(/,\s*$/, "");
      output += prefix;
      cursor = close + 1;
    }
    check.lastIndex = close + 1;
  }
  return output + source.slice(cursor);
}

export function toLibSqlSql(source: string, schema = false): string {
  let sql = source.trim();

  sql = sql.replace(/NOW\s*\(\s*\)/gi, "CURRENT_TIMESTAMP");
  sql = sql.replace(/\bILIKE\b/gi, "LIKE");
  sql = sql.replace(/\bFOR\s+(?:NO\s+KEY\s+)?UPDATE(?:\s+OF\s+[A-Za-z_][A-Za-z0-9_.]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_.]*)*)?(?:\s+SKIP\s+LOCKED)?\b/gi, "");
  sql = sql.replace(/\bFOR\s+SHARE(?:\s+OF\s+[A-Za-z_][A-Za-z0-9_.]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_.]*)*)?\b/gi, "");
  sql = sql.replace(/\bcurrent_schema\s*\(\s*\)/gi, "'main'");
  sql = sql.replace(/\bjsonb?_agg\s*\(/gi, "json_group_array(");
  sql = sql.replace(/\bjsonb?_build_object\s*\(/gi, "json_object(");
  sql = sql.replace(/\bjsonb?_array_elements\s*\(/gi, "json_each(");
  sql = sql.replace(/\bjsonb?_set\s*\(/gi, "json_set(");
  sql = sql.replace(/\bjsonb?_typeof\s*\(/gi, "json_type(");
  sql = sql.replace(/\bjsonb?_array_length\s*\(/gi, "json_array_length(");
  sql = sql.replace(/\bcardinality\s*\(/gi, "json_array_length(");
  sql = sql.replace(/\bBOOL_OR\s*\(/gi, "MAX(");
  sql = sql.replace(/\bBOOL_AND\s*\(/gi, "MIN(");
  sql = sql.replace(/\bSTRING_AGG\s*\(/gi, "GROUP_CONCAT(");
  sql = sql.replace(/\bGREATEST\s*\(/gi, "MAX(");
  sql = sql.replace(/\bLEAST\s*\(/gi, "MIN(");
  sql = sql.replace(/\bto_regclass\s*\(\s*'([A-Za-z_][A-Za-z0-9_]*)'\s*\)\s+IS\s+NOT\s+NULL/gi,
    (_match, table: string) => "EXISTS (SELECT 1 FROM sqlite_master WHERE name = '" + table + "')");

  sql = sql.replace(/CURRENT_TIMESTAMP\s*\+\s*INTERVAL\s*'([0-9]+)\s*(second|minute|hour|day)s?'/gi,
    (_match, amount: string, unit: string) => "datetime(CURRENT_TIMESTAMP, '+" + amount + " " + unit.toLowerCase() + "s')");
  sql = sql.replace(/CURRENT_TIMESTAMP\s*-\s*INTERVAL\s*'([0-9]+)\s*(second|minute|hour|day)s?'/gi,
    (_match, amount: string, unit: string) => "datetime(CURRENT_TIMESTAMP, '-" + amount + " " + unit.toLowerCase() + "s')");
  sql = sql.replace(/CURRENT_TIMESTAMP\s*([+-])\s*\(\s*(\$\d+)\s*\*\s*INTERVAL\s*'1\s*second'\s*\)/gi,
    (_match, sign: string, parameter: string) => "datetime(CURRENT_TIMESTAMP, '" + sign + "' || CAST(" + parameter + " AS TEXT) || ' seconds')");

  sql = sql.replace(/([\w.]+)\s*<>\s*ANY\s*\(\s*(\$\d+)(?:\s*::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|JSONB?|BOOLEAN|UUID|DATE|TIMESTAMPTZ|TIMESTAMP)(?:\s*\[\])?)?\s*\)/gi,
    (_match, column: string, parameter: string) => "EXISTS (SELECT 1 FROM json_each(" + parameter + ") AS values_list WHERE values_list.value <> " + column + ")");
  sql = sql.replace(/(\$\d+)(?:\s*::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|JSONB?|BOOLEAN|UUID|DATE|TIMESTAMPTZ|TIMESTAMP)(?:\s*\[\])?)?\s*=\s*ANY\s*\(\s*([\w.]+)\s*\)/gi,
    (_match, parameter: string, column: string) => "EXISTS (SELECT 1 FROM json_each(" + column + ") AS values_list WHERE values_list.value = " + parameter + ")");
  sql = sql.replace(/([\w.]+)\s*=\s*ANY\s*\(\s*(\$\d+)(?:\s*::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|JSONB?|BOOLEAN|UUID|DATE|TIMESTAMPTZ|TIMESTAMP)(?:\s*\[\])?)?\s*\)/gi,
    (_match, column: string, parameter: string) => column + " IN (SELECT value FROM json_each(" + parameter + "))");
  sql = sql.replace(/([\w.]+)\s*\[\s*([\w.]+)\s*\+\s*1\s*\]/gi,
    (_match, column: string, index: string) => "json_extract(" + column + ", '$[' || " + index + " || ']')");
  sql = sql.replace(/([\w.]+)\s*&&\s*(\$\d+)(?:\s*::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|JSONB?|BOOLEAN|UUID)(?:\s*\[\])?)?/gi,
    (_match, column: string, other: string) => "EXISTS (SELECT 1 FROM json_each(" + column + ") AS left_values JOIN json_each(" + other + ") AS right_values ON left_values.value = right_values.value)");
  sql = sql.replace(/\bARRAY\s*\[\s*\]/gi, "'[]'");
  sql = translateArrayExpressions(sql, schema);

  if (schema) {
    sql = removeUnsupportedCheckConstraints(sql);
    sql = sql.replace(/\bBIGSERIAL\b\s+PRIMARY\s+KEY/gi, "INTEGER PRIMARY KEY AUTOINCREMENT");
    sql = sql.replace(/\bSERIAL\b\s+PRIMARY\s+KEY/gi, "INTEGER PRIMARY KEY AUTOINCREMENT");
    sql = sql.replace(/\b(?:BIGINT|INT8|INTEGER|INT4)\s+GENERATED\s+BY\s+DEFAULT\s+AS\s+IDENTITY\s+PRIMARY\s+KEY/gi,
      "INTEGER PRIMARY KEY AUTOINCREMENT");
    sql = sql.replace(/\b(?:BIGINT|INT8|INTEGER|INT4)\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY\s+PRIMARY\s+KEY/gi,
      "INTEGER PRIMARY KEY AUTOINCREMENT");
    sql = sql.replace(/\b(?:BIGINT|INT8|INT4|SMALLINT|SERIAL|BIGSERIAL)\b/gi, "INTEGER");
    sql = sql.replace(/\b(?:TIMESTAMPTZ|TIMESTAMP\s+WITH\s+TIME\s+ZONE|TIMESTAMP)\b/gi, "TEXT");
    sql = sql.replace(/\bJSONB?\b/gi, "TEXT");
    sql = sql.replace(/\bBYTEA\b/gi, "BLOB");
    sql = sql.replace(/\bBOOLEAN\b/gi, "INTEGER");
    sql = sql.replace(/\b(?:VARCHAR|CHARACTER\s+VARYING|CHAR)\s*\(\s*\d+\s*\)/gi, "TEXT");
    sql = sql.replace(/\b(?:TEXT|INTEGER|UUID)\s*\[\]/gi, "TEXT");
    sql = sql.replace(/\bUUID\b/gi, "TEXT");
    sql = translateRegexOperators(sql);
  } else {
    sql = translateRegexOperators(sql);
  }

  sql = sql.replace(/::\s*(?:TEXT|INT|INTEGER|BIGINT|SMALLINT|JSONB?|BOOLEAN|UUID|DATE|TIMESTAMPTZ|TIMESTAMP)(?:\s*\[\])?/gi, "");
  sql = sql.replace(/\bALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+/gi,
    "ALTER TABLE $1 ADD COLUMN ");
  return sql.replace(/\s+FOR\s+(?:NO\s+KEY\s+)?UPDATE\b/gi, "")
    .replace(/\s+FOR\s+SHARE\b/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim()
    .replace(/;?$/, ";");
}
