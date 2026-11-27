"use client";

import { useMemo } from "react";
import type { Command } from "../../../Types/dashboard";

export interface CommandFilters {
  search: string;
  category: string;
  state: string;
}

export function useCommandSettings(commands: Command[], filters: CommandFilters) {
  const categories = useMemo(
    () => Array.from(new Set(commands.map(item => item.section || "Other"))).sort((a, b) => a.localeCompare(b)),
    [commands],
  );
  const filteredCommands = useMemo(() => {
    const needle = filters.search.trim().toLocaleLowerCase("en-US");
    return commands.filter(item => {
      const searchable = [item.fullname, item.name, item.description, item.section, item.type, item.scope].join(" ").toLocaleLowerCase("en-US");
      const stateMatch = filters.state === "All"
        || (filters.state === "Protected" && Boolean(item.protected))
        || (filters.state === "Enabled" && Boolean(item.enabled) && !item.protected)
        || (filters.state === "Disabled" && !item.enabled && !item.protected);
      return (filters.category === "All" || (item.section || "Other") === filters.category)
        && stateMatch
        && searchable.includes(needle);
    });
  }, [commands, filters.search, filters.category, filters.state]);

  return { categories, filteredCommands };
}
