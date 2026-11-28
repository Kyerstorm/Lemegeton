import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const platformLibrary = process.platform === "win32" ? "lemegeton_storage_node.dll"
  : process.platform === "darwin" ? "liblemegeton_storage_node.dylib"
    : "liblemegeton_storage_node.so";
const output = join(root, "build", "Release");
mkdirSync(output, { recursive: true });

function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", shell: process.platform === "win32" });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(command + " " + args.join(" ") + " failed with exit code " + result.status);
}

const storageAddon = join(output, "lemegeton_storage.node");
if (process.env.LEMEGETON_PREBUILT_LIBSQL_ADDON === "1") {
  if (!existsSync(storageAddon)) throw new Error("The prebuilt libSQL native addon is missing at " + storageAddon);
} else {
  run("cargo", ["build", "--release", "-p", "lemegeton-storage-node"]);
  const rustOutput = join(root, "target", "release", platformLibrary);
  if (!existsSync(rustOutput)) throw new Error("The libSQL native addon was not produced at " + rustOutput);
  copyFileSync(rustOutput, storageAddon);
}

const nodeGyp = join(root, "node_modules", "node-gyp", "bin", "node-gyp.js");
if (!existsSync(nodeGyp)) throw new Error("node-gyp is missing. Install the root development dependencies first.");
run(process.execPath, [nodeGyp, "rebuild", "--directory", join(root, "src", "utility", "database", "rocksdb")]);
const rocksOutput = join(root, "src", "utility", "database", "rocksdb", "build", "Release", "lemegeton_rocksdb.node");
if (!existsSync(rocksOutput)) throw new Error("The RocksDB native addon was not produced at " + rocksOutput);
copyFileSync(rocksOutput, join(output, "lemegeton_rocksdb.node"));
