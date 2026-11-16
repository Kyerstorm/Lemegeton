export type MediaComparisonCategory = "anime" | "manga" | "light_novel" | "book" | "movie" | "tv" | "game";

export interface MediaComparisonEntry {
  category: MediaComparisonCategory;
  title: string;
}

const CATEGORY_ALIASES: Readonly<Record<string, MediaComparisonCategory>> = {
  anime: "anime",
  manga: "manga",
  "light novel": "light_novel",
  "light novels": "light_novel",
  light_novel: "light_novel",
  book: "book",
  books: "book",
  novel: "book",
  novels: "book",
  film: "movie",
  films: "movie",
  movie: "movie",
  movies: "movie",
  tv: "tv",
  television: "tv",
  "tv show": "tv",
  "tv shows": "tv",
  game: "game",
  games: "game",
};

export function parseMediaComparisonEntries(input: string): MediaComparisonEntry[] {
  const lines = input.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 2 || lines.length > 4) {
    throw new Error("Enter between two and four titles, one per line, as category | title.");
  }

  return lines.map((line, index) => {
    const separator = line.indexOf("|");
    if (separator < 1) {
      throw new Error("Comparison line " + (index + 1) + " must use category | title.");
    }
    const categoryText = line.slice(0, separator).trim().toLowerCase();
    const title = line.slice(separator + 1).trim();
    const category = CATEGORY_ALIASES[categoryText];
    if (!category) {
      throw new Error("Comparison line " + (index + 1) + " has an unsupported category.");
    }
    if (title.length < 2 || title.length > 100) {
      throw new Error("Each comparison title must contain 2–100 characters.");
    }
    return { category, title };
  });
}
