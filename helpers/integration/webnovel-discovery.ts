import { load } from "cheerio";
import { fetchJson, fetchPublicPage, type ScrapeResult } from "./web-scraper.js";

export type WebNovelProvider = "NovelFire" | "Novel Archive" | "Wuxia Click" | "Novel Updates" | "ScribbleHub";

export interface WebNovelMedia {
provider: WebNovelProvider;
title: string;
sourceUrl: string;
description: string | null;
image: string | null;
author: string | null;
status: string | null;
genres: string[];
rating: number | null;
chapterCount: number | null;
latestUpdate: string | null;
latestChapters: string[];
}

type NovelFireItem = {
title: string;
sourceUrl: string;
image: string | null;
};

function clean(value: unknown, limit = 1_000): string | null {
if (typeof value !== "string") return null;
const text = value.replace(/<[^>]*>/g, " ").replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/\s+/g, " ").trim();
return text ? text.slice(0, limit) : null;
}

function absoluteUrl(value: unknown, base: string): string | null {
if (typeof value !== "string" || !value.trim()) return null;
try {
const url = new URL(value, base);
if (url.protocol !== "https:" && url.protocol !== "http:") return null;
return url.toString();
} catch {
return null;
}
}

function isSafeNovel(title: string, genres: string[], description: string | null): boolean {
const markers = /\b(adult|mature|smut|ecchi|hentai|erotica|erotic|nsfw|pornographic|explicit)\b|\b18\s*\+|\br\s*18\b|\bnc\s*17\b/i;
return !markers.test(title) && !genres.some(genre => markers.test(genre)) && !markers.test(description ?? "");
}

function makeRecord(provider: WebNovelProvider, values: Partial<WebNovelMedia> & { title: string; sourceUrl: string }): WebNovelMedia | null {
const genres = (values.genres ?? []).map(value => clean(value, 80)).filter((value): value is string => Boolean(value)).slice(0, 20);
const description = clean(values.description, 1_400);
if (!isSafeNovel(values.title, genres, description)) return null;
return {
provider,
title: clean(values.title, 256) ?? "Untitled",
sourceUrl: values.sourceUrl,
description,
image: absoluteUrl(values.image, values.sourceUrl),
author: clean(values.author, 160),
status: clean(values.status, 80),
genres,
rating: typeof values.rating === "number" && Number.isFinite(values.rating) ? values.rating : null,
chapterCount: typeof values.chapterCount === "number" && Number.isFinite(values.chapterCount) ? values.chapterCount : null,
latestUpdate: values.latestUpdate ?? null,
latestChapters: (values.latestChapters ?? []).map(value => clean(value, 180)).filter((value): value is string => Boolean(value)).slice(0, 5),
};
}

export function parseNovelFireSearch(html: string, baseUrl = "https://novelfire.net/"): NovelFireItem[] {
const $ = load(html);
const results: NovelFireItem[] = [];
const seen = new Set<string>();
$(".novel-list.chapters .novel-item, .novel-item").each((_, element) => {
const card = $(element);
const anchor = card.children("a[href]").first().length ? card.children("a[href]").first() : card.find("h4 a[href]").first().length ? card.find("h4 a[href]").first() : card.find("a[href]").first();
const href = anchor.attr("href");
const sourceUrl = absoluteUrl(href, baseUrl);
if (!sourceUrl) return;
const url = new URL(sourceUrl);
if (url.hostname !== "novelfire.net" && url.hostname !== "www.novelfire.net") return;
const title = clean(anchor.attr("title") || card.find("h4").first().text() || anchor.text(), 256);
if (!title || seen.has(sourceUrl)) return;
seen.add(sourceUrl);
const imageRaw = card.find(".novel-cover img").first().attr("data-src") || card.find(".novel-cover img").first().attr("src") || card.find("img").first().attr("data-src") || card.find("img").first().attr("src");
results.push({ title, sourceUrl, image: absoluteUrl(imageRaw, baseUrl) });
});
return results.slice(0, 10);
}

function extractChapterCount(value: string | null): number | null {
if (!value) return null;
const matches = [...value.matchAll(/([\d,]+)\s+chapters?/gi)];
if (!matches.length) return null;
const number = Number(matches[matches.length - 1]![1]!.replace(/,/g, ""));
return Number.isSafeInteger(number) ? number : null;
}

async function enrichNovelFire(item: NovelFireItem): Promise<WebNovelMedia | null> {
const page = await fetchPublicPage(item.sourceUrl, { includeHtml: true, includeText: false, timeoutMs: 10_000 });
const $ = load(page.html ?? "");
const summary = clean($(".summary .content").text(), 1_400);
const author = clean($(".author .property-item > span").first().text(), 160);
const status = clean($(".header-stats .ongoing").text() || $(".header-stats .completed").text(), 80);
const genres = $(".categories .property-item").map((_, element) => clean($(element).text(), 80)).get().filter((value): value is string => Boolean(value));
const scoreText = clean($(".nub").first().text(), 20);
const score = scoreText ? Number(scoreText) : null;
const statsText = clean($(".header-stats").text(), 500);
let chapterCount = extractChapterCount(statsText);
const latestChapters: string[] = [];
const postId = $("#novel-report").attr("report-post_id");
if (postId && /^\d+$/.test(postId)) {
const params = new URLSearchParams({
draw: "1",
"columns[0][data]": "n_sort",
"columns[0][name]": "cmm_posts_detail.n_sort",
"columns[0][searchable]": "true",
"columns[0][orderable]": "true",
"columns[1][data]": "bookmark_created_at",
"columns[1][name]": "bookmark_chapters.created_at",
"order[0][column]": "0",
"order[0][dir]": "asc",
start: "0",
length: "5",
"search[value]": "",
"search[regex]": "false",
post_id: postId,
only_bookmark: "false",
_: String(Date.now()),
});
try {
const chapters = await fetchJson<{ data?: Array<{ title?: string; slug?: string; n_sort?: string | number }>; recordsFiltered?: number; recordsTotal?: number }>(
"https://novelfire.net/ajax/listChapterDataAjax?" + params.toString(),
{ timeoutMs: 8_000, retries: 0 },
);
if (typeof chapters.recordsFiltered === "number") chapterCount = chapters.recordsFiltered;
else if (typeof chapters.recordsTotal === "number") chapterCount = chapters.recordsTotal;
for (const chapter of chapters.data ?? []) {
const name = clean(chapter.title || chapter.slug, 180);
if (name) latestChapters.push(name);
}
} catch {
// Keep the detail-page metadata when the chapter endpoint is temporarily unavailable.
}
}
return makeRecord("NovelFire", {
title: clean($(".novel-title").first().text() || $(".cover > img").first().attr("alt"), 256) ?? item.title,
sourceUrl: page.canonicalUrl || item.sourceUrl,
description: summary,
image: $(".cover > img").first().attr("data-src") || $(".cover > img").first().attr("src") || item.image,
author,
status,
genres,
rating: score !== null && Number.isFinite(score) ? score : null,
chapterCount,
latestChapters,
});
}

async function searchNovelFire(query: string): Promise<WebNovelMedia[]> {
const url = new URL("https://novelfire.net/search");
url.searchParams.set("keyword", query);
url.searchParams.set("page", "1");
let page: ScrapeResult;
try {
page = await fetchPublicPage(url.toString(), {
selectors: { cards: ".novel-list.chapters .novel-item" },
includeText: false,
includeHtml: true,
timeoutMs: 10_000,
retries: 1,
});
} catch (error) {
try {
page = await fetchPublicPage(url.toString(), {
engine: "browser",
selectors: { cards: ".novel-list.chapters .novel-item" },
includeText: false,
includeHtml: true,
timeoutMs: 15_000,
retries: 0,
});
} catch {
throw error;
}
}
let items = parseNovelFireSearch(page.html ?? "", page.url);
if (!items.length && page.engine === "fetch") {
try {
const rendered = await fetchPublicPage(url.toString(), { engine: "browser", includeHtml: true, includeText: false, timeoutMs: 15_000, retries: 0 });
items = parseNovelFireSearch(rendered.html ?? "", rendered.url);
} catch {
// Static search remains available without a configured browser runtime.
}
}
const details = await Promise.allSettled(items.slice(0, 4).map(enrichNovelFire));
return items.slice(0, 4).flatMap((item, index) => {
const result = details[index];
if (result?.status === "fulfilled" && result.value) return [result.value];
const fallback = makeRecord("NovelFire", { title: item.title, sourceUrl: item.sourceUrl, image: item.image });
return fallback ? [fallback] : [];
});
}

export function parseScribbleHubSearch(html: string, baseUrl = "https://www.scribblehub.com/"): NovelFireItem[] {
const $ = load(html);
const results: NovelFireItem[] = [];
const seen = new Set<string>();
$(".search_main_box").each((_, element) => {
const card = $(element);
const anchor = card.find(".search_title > a[href]").first();
const sourceUrl = absoluteUrl(anchor.attr("href"), baseUrl);
if (!sourceUrl) return;
const host = new URL(sourceUrl).hostname;
if (host !== "scribblehub.com" && host !== "www.scribblehub.com") return;
const title = clean(anchor.text() || anchor.attr("title"), 256);
if (!title || seen.has(sourceUrl)) return;
seen.add(sourceUrl);
const image = card.find(".search_img > img").first().attr("data-src") || card.find(".search_img > img").first().attr("src");
results.push({ title, sourceUrl, image: absoluteUrl(image, baseUrl) });
});
return results.slice(0, 10);
}

function parseScribbleHubReleaseDate(value: string | null): string | null {
if (!value) return null;
const relative = value.match(/(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago/i);
if (relative) {
const amount = Number(relative[1]);
const unit = relative[2]!.toLowerCase();
const duration: Record<string, number> = {
second: 1_000,
minute: 60_000,
hour: 3_600_000,
day: 86_400_000,
week: 604_800_000,
month: 2_592_000_000,
year: 31_536_000_000,
};
return new Date(Date.now() - amount * (duration[unit] ?? 0)).toISOString();
}
const absolute = value.match(/([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*(AM|PM))?/i);
if (!absolute) return null;
const monthNames = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
const month = monthNames.indexOf(absolute[1]!.toLowerCase());
if (month < 0) return null;
let hour = absolute[4] ? Number(absolute[4]) % 12 : 0;
if (absolute[6]?.toUpperCase() === "PM") hour += 12;
const date = new Date(Date.UTC(Number(absolute[3]), month, Number(absolute[2]), hour, Number(absolute[5] ?? 0)));
return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

async function enrichScribbleHub(item: NovelFireItem): Promise<WebNovelMedia | null> {
const page = await fetchPublicPage(item.sourceUrl, { includeHtml: true, includeText: false, timeoutMs: 10_000, retries: 1 });
const $ = load(page.html ?? "");
const title = clean($(".fic_title").first().text(), 256) ?? item.title;
const image = $(".fic_image > img").first().attr("data-src") || $(".fic_image > img").first().attr("src") || item.image;
const description = clean($(".wi_fic_desc").text(), 1_400);
const author = clean($(".auth_name_fic").text(), 160);
const genres = $(".fic_genre").map((_, element) => clean($(element).text(), 80)).get().filter((value): value is string => Boolean(value));
const statusText = clean($("i.status").closest("li").text(), 100)?.toLowerCase() ?? "";
const status = statusText.includes("ongoing") ? "Ongoing" : statusText.includes("hiatus") ? "Hiatus" : statusText.includes("completed") ? "Completed" : null;
const latestChapters: string[] = [];
let chapterCount: number | null = null;
let latestUpdate: string | null = null;
const postId = $("#mypostid").attr("value");
if (postId && /^\d+$/.test(postId)) {
const response = await fetchPublicPage("https://www.scribblehub.com/wp-admin/admin-ajax.php", {
method: "POST",
body: new URLSearchParams({ action: "wi_getreleases_pagination", pagenum: "-1", mypostid: postId }).toString(),
headers: {
"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
"X-Requested-With": "XMLHttpRequest",
"Referer": item.sourceUrl,
"Origin": "https://www.scribblehub.com",
},
includeHtml: true,
includeText: false,
timeoutMs: 12_000,
retries: 0,
});
const chapters = load(response.html ?? "");
const all = chapters(".toc_w").toArray().map(element => {
const chapter = chapters(element);
const link = chapter.find("a.toc_a").first();
const name = clean(link.text(), 180);
const dateText = clean(chapter.find(".fic_date_pub").attr("title") || chapter.find(".fic_date_pub").text(), 100);
return { name, date: parseScribbleHubReleaseDate(dateText) };
}).filter((chapter): chapter is { name: string; date: string | null } => Boolean(chapter.name));
chapterCount = all.length;
latestUpdate = [...all].reverse().find(chapter => chapter.date)?.date ?? null;
latestChapters.push(...all.slice(-5).reverse().map(chapter => chapter.name));
}
return makeRecord("ScribbleHub", {
title,
sourceUrl: page.canonicalUrl || item.sourceUrl,
description,
image,
author,
status,
genres,
chapterCount,
latestUpdate,
latestChapters,
});
}

async function searchScribbleHub(query: string): Promise<WebNovelMedia[]> {
const url = new URL("https://www.scribblehub.com/series-finder/");
url.searchParams.set("sf", "1");
url.searchParams.set("sh", query);
url.searchParams.set("pg", "1");
const page = await fetchPublicPage(url.toString(), { includeHtml: true, includeText: false, timeoutMs: 10_000, retries: 1 });
const items = parseScribbleHubSearch(page.html ?? "", page.url);
const details = await Promise.allSettled(items.slice(0, 4).map(enrichScribbleHub));
return items.slice(0, 4).flatMap((item, index) => {
const result = details[index];
if (result?.status === "fulfilled" && result.value) return [result.value];
const fallback = makeRecord("ScribbleHub", { title: item.title, sourceUrl: item.sourceUrl, image: item.image });
return fallback ? [fallback] : [];
});
}

type NovelArchiveNovel = {
id?: string | number;
title?: string;
cover_url?: string;
image_url?: string;
author?: string;
genres?: string[] | string;
description?: string;
chapter_names?: string[];
status?: string;
updated_at?: string;
rating?: number | string;
};

type NovelArchiveResponse = { novels?: NovelArchiveNovel[]; novel?: NovelArchiveNovel };

export function parseNovelArchiveSearch(payload: NovelArchiveResponse, baseUrl = "https://novelarchive.cc/"): WebNovelMedia[] {
return (payload.novels ?? []).flatMap(novel => {
if (!novel.title || (typeof novel.id !== "string" && typeof novel.id !== "number")) return [];
const sourceUrl = baseUrl + "novel?id=" + encodeURIComponent(String(novel.id));
const genres = Array.isArray(novel.genres) ? novel.genres : typeof novel.genres === "string" ? novel.genres.split(/[,|]/) : [];
const rating = typeof novel.rating === "string" ? Number(novel.rating) : novel.rating;
const record = makeRecord("Novel Archive", {
title: novel.title,
sourceUrl,
description: novel.description,
image: novel.cover_url || novel.image_url,
author: novel.author,
genres,
status: novel.status,
rating: typeof rating === "number" && Number.isFinite(rating) ? rating : null,
chapterCount: Array.isArray(novel.chapter_names) ? novel.chapter_names.length : null,
latestUpdate: novel.updated_at ?? null,
});
return record ? [record] : [];
});
}

async function searchNovelArchive(query: string): Promise<WebNovelMedia[]> {
const url = new URL("https://novelarchive.cc/api/novels");
url.searchParams.set("search", query);
url.searchParams.set("page", "1");
const payload = await fetchJson<NovelArchiveResponse>(url.toString(), { timeoutMs: 10_000, retries: 1 });
const initial = parseNovelArchiveSearch(payload);
const details = await Promise.allSettled(initial.slice(0, 4).map(async item => {
const id = new URL(item.sourceUrl).searchParams.get("id");
if (!id || !/^[0-9a-fA-F]+$/.test(id)) return item;
const detail = await fetchJson<NovelArchiveResponse>("https://novelarchive.cc/api/novels/" + encodeURIComponent(id), { timeoutMs: 10_000, retries: 1 });
const novel = detail.novel ?? detail as NovelArchiveNovel;
if (!novel.title) return item;
const genres = Array.isArray(novel.genres) ? novel.genres : typeof novel.genres === "string" ? novel.genres.split(/[,|]/) : item.genres;
const rating = typeof novel.rating === "string" ? Number(novel.rating) : novel.rating;
return makeRecord("Novel Archive", {
title: novel.title,
sourceUrl: item.sourceUrl,
description: novel.description ?? item.description,
image: novel.cover_url || novel.image_url || item.image,
author: novel.author ?? item.author,
genres,
status: novel.status ?? item.status,
rating: typeof rating === "number" && Number.isFinite(rating) ? rating : item.rating,
chapterCount: Array.isArray(novel.chapter_names) ? novel.chapter_names.length : item.chapterCount,
latestUpdate: novel.updated_at ?? item.latestUpdate,
}) ?? item;
}));
return details.flatMap(result => result.status === "fulfilled" ? [result.value] : []);
}

type WuxiaNovel = {
title?: string;
name?: string;
slug?: string;
description?: string;
image?: string;
coverKey?: string;
author?: { name?: string } | string;
genres?: Array<{ name?: string }> | string[];
categories?: Array<{ name?: string }>;
tags?: Array<{ name?: string }>;
chapters?: number;
rating?: number;
status?: string;
updatedAt?: string;
};

function findWuxiaPageData(html: string): Record<string, any> | null {
const $ = load(html);
const raw = $("script#__NEXT_DATA__").first().html();
if (!raw) return null;
try {
return JSON.parse(raw).props?.pageProps ?? null;
} catch {
return null;
}
}

export function parseWuxiaClickPageData(pageProps: Record<string, any>): WebNovelMedia[] {
const list = pageProps.result?.items
?? pageProps.listing?.items
?? pageProps.dehydratedState?.queries?.[0]?.state?.data?.results
?? [];
if (!Array.isArray(list)) return [];
return list.flatMap((value: WuxiaNovel) => {
const title = clean(value.title || value.name, 256);
const slug = clean(value.slug, 200);
if (!title || !slug) return [];
const sourceUrl = "https://wuxia.click/novel/" + encodeURIComponent(slug);
const genres = Array.isArray(value.genres) ? value.genres.map(item => typeof item === "string" ? item : item.name ?? "")
: Array.isArray(value.categories) ? value.categories.map(item => item.name ?? "")
: Array.isArray(value.tags) ? value.tags.map(item => item.name ?? "") : [];
const image = value.coverKey ? "https://cdn.wuxiaworld.eu/" + value.coverKey + "-480.webp" : value.image;
const author = typeof value.author === "string" ? value.author : value.author?.name;
const record = makeRecord("Wuxia Click", {
title,
sourceUrl,
description: value.description,
image,
author,
genres,
status: value.status,
chapterCount: typeof value.chapters === "number" ? value.chapters : null,
rating: typeof value.rating === "number" ? value.rating : null,
latestUpdate: value.updatedAt ?? null,
});
return record ? [record] : [];
});
}

async function searchWuxiaClick(query: string): Promise<WebNovelMedia[]> {
const url = "https://wuxia.click/search/" + encodeURIComponent(query) + "?page=1";
const page = await fetchPublicPage(url, { includeHtml: true, includeText: false, timeoutMs: 10_000, retries: 1 });
const props = findWuxiaPageData(page.html ?? "");
const results = props ? parseWuxiaClickPageData(props) : [];
const details = await Promise.allSettled(results.slice(0, 4).map(async item => {
const slug = new URL(item.sourceUrl).pathname.split("/").filter(Boolean).at(-1);
if (!slug) return item;
const detailPage = await fetchPublicPage(item.sourceUrl, { includeHtml: true, includeText: false, timeoutMs: 10_000, retries: 1 });
const data = findWuxiaPageData(detailPage.html ?? "");
const novel = data?.novel as WuxiaNovel | undefined;
const toc = data?.toc as { items?: Array<{ title?: string; number?: number; createdAt?: string }>; ranges?: unknown[] } | undefined;
if (!novel) return item;
const title = clean(novel.title || novel.name, 256) ?? item.title;
const genres = Array.isArray(novel.genres) ? novel.genres.map(entry => typeof entry === "string" ? entry : entry.name ?? "")
: Array.isArray(novel.categories) ? novel.categories.map(entry => entry.name ?? "") : item.genres;
const latestChapters = (toc?.items ?? []).slice(-5).reverse().flatMap(chapter => {
const name = clean(chapter.title || (typeof chapter.number === "number" ? "Chapter " + chapter.number : ""), 180);
return name ? [name] : [];
});
return makeRecord("Wuxia Click", {
title,
sourceUrl: item.sourceUrl,
description: novel.description ?? item.description,
image: novel.coverKey ? "https://cdn.wuxiaworld.eu/" + novel.coverKey + "-480.webp" : novel.image ?? item.image,
author: typeof novel.author === "string" ? novel.author : novel.author?.name ?? item.author,
genres,
status: novel.status ?? item.status,
chapterCount: toc?.items?.length ?? (typeof novel.chapters === "number" ? novel.chapters : item.chapterCount),
rating: typeof novel.rating === "number" ? novel.rating : item.rating,
latestUpdate: novel.updatedAt ?? item.latestUpdate,
latestChapters,
}) ?? item;
}));
return details.flatMap(result => result.status === "fulfilled" ? [result.value] : []);
}

export function parseNovelUpdatesSearch(html: string, baseUrl = "https://www.novelupdates.com/"): WebNovelMedia[] {
const $ = load(html);
const records: WebNovelMedia[] = [];
const seen = new Set<string>();
const cards = $(".search_main_box_nu, .search_main_box, .search_result, .series_result, article");
const candidates = cards.length ? cards : $("a[href*='/series/']");
candidates.each((_, element) => {
const card = $(element);
const anchor = card.is("a[href*='/series/']") ? card : card.find("a[href*='/series/']").first();
const href = anchor.attr("href");
const sourceUrl = absoluteUrl(href, baseUrl);
if (!sourceUrl) return;
const parsed = new URL(sourceUrl);
if (parsed.hostname !== "novelupdates.com" && parsed.hostname !== "www.novelupdates.com") return;
if (!parsed.pathname.toLowerCase().includes("/series/")) return;
const title = clean(anchor.text() || anchor.attr("title") || parsed.pathname.split("/").filter(Boolean).at(-1)?.replace(/[-_]/g, " "), 256);
if (!title || seen.has(sourceUrl)) return;
seen.add(sourceUrl);
const text = clean(card.text(), 1_800);
const genres = card.find(".search_genre a, .search_genres a, a[href*='/genre/']").map((_, node) => clean($(node).text(), 80) ?? "").get().filter(Boolean);
const author = clean(card.find(".search_author, .series_author, [class*='author']").first().text(), 160);
const description = clean(card.find(".search_body, .search_body_nu, .search_desc, .series_synopsis").first().text(), 1_200);
const chapterMatch = text?.match(/([\d,]+)\s+chapters?/i);
const chapterCount = chapterMatch ? Number(chapterMatch[1]!.replace(/,/g, "")) : null;
const record = makeRecord("Novel Updates", {
title,
sourceUrl: sourceUrl.replace(/#.*$/, ""),
description,
image: card.find("img").first().attr("data-src") || card.find("img").first().attr("src"),
author,
status: clean(card.find(".search_status, .series_status, [class*='status']").first().text(), 80),
genres,
chapterCount: chapterCount !== null && Number.isFinite(chapterCount) ? chapterCount : null,
});
if (record) records.push(record);
});
return records.slice(0, 10);
}

async function searchNovelUpdates(query: string): Promise<WebNovelMedia[]> {
const url = new URL("https://www.novelupdates.com/series-finder/");
url.searchParams.set("sf", "1");
url.searchParams.set("sh", query);
url.searchParams.set("sort", "sdate");
url.searchParams.set("order", "desc");
let page: ScrapeResult;
try {
page = await fetchPublicPage(url.toString(), { includeHtml: true, includeText: false, timeoutMs: 8_000, retries: 0 });
} catch {
const fallback = new URL("https://www.novelupdates.com/");
fallback.searchParams.set("s", query);
fallback.searchParams.set("post_type", "series");
page = await fetchPublicPage(fallback.toString(), { includeHtml: true, includeText: false, timeoutMs: 8_000, retries: 0 });
}
let results = parseNovelUpdatesSearch(page.html ?? "", page.url);
if (!results.length) {
try {
const browserPage = await fetchPublicPage(page.url, { engine: "browser", includeHtml: true, includeText: false, timeoutMs: 15_000, retries: 0 });
results = parseNovelUpdatesSearch(browserPage.html ?? "", browserPage.url);
} catch {
// Static response is still useful when no browser runtime is configured.
}
}
return results;
}

export class WebNovelDiscoveryClient {
async search(query: string): Promise<WebNovelMedia[]> {
const normalized = query.trim().replace(/\s+/g, " ");
if (normalized.length < 2) return [];
const providers = await Promise.allSettled([
searchNovelFire(normalized),
searchNovelArchive(normalized),
searchWuxiaClick(normalized),
searchNovelUpdates(normalized),
searchScribbleHub(normalized),
]);
const records = providers.flatMap(result => result.status === "fulfilled" ? result.value : []);
const unique = new Map<string, WebNovelMedia>();
for (const record of records) {
const key = record.title.toLocaleLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "");
const existing = unique.get(key);
if (!existing) unique.set(key, record);
else {
unique.set(key, {
...existing,
description: existing.description ?? record.description,
image: existing.image ?? record.image,
author: existing.author ?? record.author,
status: existing.status ?? record.status,
genres: existing.genres.length ? existing.genres : record.genres,
chapterCount: existing.chapterCount ?? record.chapterCount,
latestUpdate: existing.latestUpdate ?? record.latestUpdate,
latestChapters: existing.latestChapters.length ? existing.latestChapters : record.latestChapters,
});
}
}
return [...unique.values()].slice(0, 10);
}
}
