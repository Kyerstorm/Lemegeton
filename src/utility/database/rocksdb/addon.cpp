#include <napi.h>
#include <rocksdb/db.h>
#include <rocksdb/iterator.h>
#include <rocksdb/write_batch.h>
#include <rocksdb/utilities/checkpoint.h>

#if __has_include("bla_shield.h")
#include "bla_shield.h"
#define LEMEGETON_HAS_BLA_SHIELD 1
#endif

#include <algorithm>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>

namespace {

constexpr std::size_t kChunkBytes = 1024 * 1024;
constexpr std::size_t kMaximumReadBytes = 256ULL * 1024ULL * 1024ULL;

std::string object_prefix(const std::string& key) {
  return "object/" + key + "/";
}

std::string metadata_key(const std::string& key) {
  return object_prefix(key) + "!meta";
}

std::string chunk_key(const std::string& key, std::size_t index) {
  std::ostringstream suffix;
  suffix << "chunk/" << std::setw(8) << std::setfill('0') << index;
  return object_prefix(key) + suffix.str();
}

enum class Operation { Put, PutChunk, Finish, Get, Info, ReadChunk, Delete, Checkpoint };

class ObjectWorker final : public Napi::AsyncWorker {
 public:
  ObjectWorker(
      Napi::Env env,
      Napi::Promise::Deferred deferred,
      std::shared_ptr<rocksdb::DB> database,
      Operation operation,
      std::string key,
      std::string bytes = {},
      std::string metadata = {},
      std::size_t chunk = 0)
      : Napi::AsyncWorker(env, "lemegeton-rocksdb"),
        deferred_(std::move(deferred)),
        database_(std::move(database)),
        operation_(operation),
        key_(std::move(key)),
        bytes_(std::move(bytes)),
        metadata_(std::move(metadata)),
        chunk_(chunk) {}

  void Execute() override {
    if (!database_) {
      SetError("RocksDB storage is closed.");
      return;
    }

    rocksdb::Status status;
    switch (operation_) {
      case Operation::Put:
        put_object();
        break;
      case Operation::PutChunk:
        put_chunk();
        break;
      case Operation::Finish:
        finish_object();
        break;
      case Operation::Get:
        get_object();
        break;
      case Operation::Info:
        status = database_->Get(rocksdb::ReadOptions(), metadata_key(key_), &result_);
        if (status.IsNotFound()) found_ = false;
        else if (!status.ok()) SetError(status.ToString());
        else {
          found_ = true;
          const auto first = result_.find('\n');
          const auto second = first == std::string::npos ? first : result_.find('\n', first + 1);
          if (second == std::string::npos) {
            SetError("RocksDB object metadata is corrupt.");
          } else {
            const std::string size = result_.substr(0, first);
            const std::string chunks = result_.substr(first + 1, second - first - 1);
            const std::string metadata = result_.substr(second + 1);
            result_ = "{\"sizeBytes\":" + size + ",\"chunkCount\":" + chunks + ",\"metadata\":" + metadata + "}";
          }
        }
        break;
      case Operation::ReadChunk:
        status = database_->Get(rocksdb::ReadOptions(), chunk_key(key_, chunk_), &result_);
        if (status.IsNotFound()) found_ = false;
        else if (!status.ok()) SetError(status.ToString());
        else found_ = true;
        break;
      case Operation::Delete:
        delete_object();
        break;
      case Operation::Checkpoint:
        create_checkpoint();
        break;
    }
  }

  void OnOK() override {
    Napi::Env env = Env();
    switch (operation_) {
      case Operation::Put:
      case Operation::PutChunk:
      case Operation::Finish:
      case Operation::Delete:
      case Operation::Checkpoint:
        deferred_.Resolve(env.Undefined());
        break;
      case Operation::Info:
        deferred_.Resolve(found_ ? Napi::String::New(env, result_) : env.Null());
        break;
      case Operation::Get:
      case Operation::ReadChunk:
        if (!found_) deferred_.Resolve(env.Null());
        else deferred_.Resolve(Napi::Buffer<std::uint8_t>::Copy(
            env, reinterpret_cast<const std::uint8_t*>(result_.data()), result_.size()));
        break;
    }
  }

  void OnError(const Napi::Error& error) override {
    deferred_.Reject(error.Value());
  }

 private:
  void put_chunk() {
    if (bytes_.empty() || chunk_ > 255) {
      SetError("RocksDB chunks must contain bytes and have a valid index.");
      return;
    }
    const rocksdb::Status status = database_->Put(
      rocksdb::WriteOptions(), chunk_key(key_, chunk_), rocksdb::Slice(bytes_));
    if (!status.ok()) SetError(status.ToString());
  }

  void finish_object() {
    std::size_t expected_size = 0;
    try {
      expected_size = static_cast<std::size_t>(std::stoull(bytes_));
    } catch (...) {
      SetError("RocksDB object size is invalid.");
      return;
    }
    if (expected_size > kMaximumReadBytes || chunk_ < 1 || chunk_ > 256 || metadata_.empty()) {
      SetError("RocksDB object metadata is invalid.");
      return;
    }
    std::size_t actual_size = 0;
    for (std::size_t index = 0; index < chunk_; ++index) {
      std::string chunk;
      const rocksdb::Status read = database_->Get(rocksdb::ReadOptions(), chunk_key(key_, index), &chunk);
      if (!read.ok() || chunk.empty() || chunk.size() > kChunkBytes) {
        SetError(read.IsNotFound() ? "RocksDB object is missing a data chunk." : read.ToString());
        return;
      }
      actual_size += chunk.size();
    }
    if (actual_size != expected_size) {
      SetError("RocksDB object size does not match its uploaded chunks.");
      return;
    }
    std::ostringstream metadata;
    metadata << expected_size << '\n' << chunk_ << '\n' << metadata_;
    const rocksdb::Status status = database_->Put(rocksdb::WriteOptions(), metadata_key(key_), metadata.str());
    if (!status.ok()) SetError(status.ToString());
  }

  void put_object() {
    rocksdb::WriteBatch batch;
    const std::string prefix = object_prefix(key_);
    std::unique_ptr<rocksdb::Iterator> iterator(database_->NewIterator(rocksdb::ReadOptions()));
    for (iterator->Seek(prefix); iterator->Valid(); iterator->Next()) {
      if (iterator->key().ToString().compare(0, prefix.size(), prefix) != 0) break;
      batch.Delete(iterator->key());
    }
    std::size_t count = 0;
    for (std::size_t offset = 0; offset < bytes_.size(); offset += kChunkBytes) {
      const std::size_t length = std::min(kChunkBytes, bytes_.size() - offset);
      batch.Put(chunk_key(key_, count++), rocksdb::Slice(bytes_.data() + offset, length));
    }
    if (!iterator->status().ok()) {
      SetError(iterator->status().ToString());
      return;
    }
    std::ostringstream metadata;
    metadata << bytes_.size() << '\n' << count << '\n' << metadata_;
    batch.Put(metadata_key(key_), metadata.str());
    const rocksdb::Status status = database_->Write(rocksdb::WriteOptions(), &batch);
    if (!status.ok()) SetError(status.ToString());
  }

  void get_object() {
    std::string metadata;
    rocksdb::Status status = database_->Get(rocksdb::ReadOptions(), metadata_key(key_), &metadata);
    if (status.IsNotFound()) {
      found_ = false;
      return;
    }
    if (!status.ok()) {
      SetError(status.ToString());
      return;
    }

    std::istringstream fields(metadata);
    std::string size_line;
    std::string count_line;
    if (!std::getline(fields, size_line) || !std::getline(fields, count_line)) {
      SetError("RocksDB object metadata is corrupt.");
      return;
    }

    std::size_t expected_size = 0;
    std::size_t count = 0;
    try {
      expected_size = static_cast<std::size_t>(std::stoull(size_line));
      count = static_cast<std::size_t>(std::stoull(count_line));
    } catch (...) {
      SetError("RocksDB object metadata contains invalid sizes.");
      return;
    }
    if (expected_size > kMaximumReadBytes || count > 256) {
      SetError("RocksDB object exceeds the maximum read size.");
      return;
    }

    result_.clear();
    result_.reserve(expected_size);
    for (std::size_t index = 0; index < count; ++index) {
      std::string chunk;
      status = database_->Get(rocksdb::ReadOptions(), chunk_key(key_, index), &chunk);
      if (!status.ok()) {
        SetError(status.IsNotFound() ? "RocksDB object is missing a data chunk." : status.ToString());
        return;
      }
      result_.append(chunk);
    }
    if (result_.size() != expected_size) {
      SetError("RocksDB object size does not match its metadata.");
      return;
    }
    found_ = true;
  }

  void create_checkpoint() {
    rocksdb::Checkpoint* raw = nullptr;
    rocksdb::Status status = rocksdb::Checkpoint::Create(database_.get(), &raw);
    if (!status.ok()) {
      SetError(status.ToString());
      return;
    }
    std::unique_ptr<rocksdb::Checkpoint> checkpoint(raw);
    status = checkpoint->CreateCheckpoint(bytes_);
    if (!status.ok()) SetError(status.ToString());
  }

  void delete_object() {
    const std::string prefix = object_prefix(key_);
    rocksdb::WriteBatch batch;
    std::unique_ptr<rocksdb::Iterator> iterator(database_->NewIterator(rocksdb::ReadOptions()));
    for (iterator->Seek(prefix); iterator->Valid(); iterator->Next()) {
      if (iterator->key().ToString().compare(0, prefix.size(), prefix) != 0) break;
      batch.Delete(iterator->key());
    }
    if (!iterator->status().ok()) {
      SetError(iterator->status().ToString());
      return;
    }
    const rocksdb::Status status = database_->Write(rocksdb::WriteOptions(), &batch);
    if (!status.ok()) SetError(status.ToString());
  }

  Napi::Promise::Deferred deferred_;
  std::shared_ptr<rocksdb::DB> database_;
  Operation operation_;
  std::string key_;
  std::string bytes_;
  std::string metadata_;
  std::size_t chunk_;
  std::string result_;
  bool found_ = false;
};

}  // namespace

class RocksStore final : public Napi::ObjectWrap<RocksStore> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports) {
    const auto type = DefineClass(env, "RocksStore", {
      InstanceMethod("putObject", &RocksStore::PutObject),
      InstanceMethod("putChunk", &RocksStore::PutChunk),
      InstanceMethod("finishObject", &RocksStore::FinishObject),
      InstanceMethod("getObject", &RocksStore::GetObject),
      InstanceMethod("getObjectInfo", &RocksStore::GetObjectInfo),
      InstanceMethod("readChunk", &RocksStore::ReadChunk),
      InstanceMethod("deleteObject", &RocksStore::DeleteObject),
      InstanceMethod("createCheckpoint", &RocksStore::CreateCheckpoint),
      InstanceMethod("close", &RocksStore::Close),
    });
    constructor = Napi::Persistent(type);
    exports.Set("RocksStore", type);
    return exports;
  }

  explicit RocksStore(const Napi::CallbackInfo& info) : Napi::ObjectWrap<RocksStore>(info) {
    Napi::Env env = info.Env();
    if (info.Length() < 1 || !info[0].IsString()) {
      Napi::TypeError::New(env, "RocksStore requires a database directory.").ThrowAsJavaScriptException();
      return;
    }
    const std::string path = info[0].As<Napi::String>().Utf8Value();
    rocksdb::Options options;
    options.create_if_missing = true;
    rocksdb::DB* raw = nullptr;
    const rocksdb::Status status = rocksdb::DB::Open(options, path, &raw);
    if (!status.ok()) {
      Napi::Error::New(env, "Could not open RocksDB: " + status.ToString()).ThrowAsJavaScriptException();
      return;
    }
    database_ = std::shared_ptr<rocksdb::DB>(raw);
  }

 private:
  Napi::Value PutObject(const Napi::CallbackInfo& info) {
    if (info.Length() < 3 || !info[0].IsString() || !info[1].IsBuffer() || !info[2].IsString()) {
      Napi::TypeError::New(info.Env(), "putObject requires (key, Buffer, metadata JSON).").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const auto buffer = info[1].As<Napi::Buffer<std::uint8_t>>();
    std::string bytes(reinterpret_cast<const char*>(buffer.Data()), buffer.Length());
    return queue(info.Env(), Operation::Put, info[0].As<Napi::String>().Utf8Value(),
      std::move(bytes), info[2].As<Napi::String>().Utf8Value());
  }

  Napi::Value PutChunk(const Napi::CallbackInfo& info) {
    if (info.Length() < 3 || !info[0].IsString() || !info[1].IsNumber() || !info[2].IsBuffer()) {
      Napi::TypeError::New(info.Env(), "putChunk requires (key, chunkIndex, Buffer).").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const double index = info[1].As<Napi::Number>().DoubleValue();
    if (index < 0 || index > 255 || index != static_cast<double>(static_cast<std::size_t>(index))) {
      Napi::RangeError::New(info.Env(), "The chunk index is invalid.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const auto buffer = info[2].As<Napi::Buffer<std::uint8_t>>();
    std::string bytes(reinterpret_cast<const char*>(buffer.Data()), buffer.Length());
    return queue(info.Env(), Operation::PutChunk, info[0].As<Napi::String>().Utf8Value(),
      std::move(bytes), {}, static_cast<std::size_t>(index));
  }

  Napi::Value FinishObject(const Napi::CallbackInfo& info) {
    if (info.Length() < 4 || !info[0].IsString() || !info[1].IsNumber()
        || !info[2].IsNumber() || !info[3].IsString()) {
      Napi::TypeError::New(info.Env(), "finishObject requires (key, sizeBytes, chunkCount, metadata JSON).").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const double size = info[1].As<Napi::Number>().DoubleValue();
    const double count = info[2].As<Napi::Number>().DoubleValue();
    if (size < 1 || size > kMaximumReadBytes || count < 1 || count > 256
        || size != static_cast<double>(static_cast<std::size_t>(size))
        || count != static_cast<double>(static_cast<std::size_t>(count))) {
      Napi::RangeError::New(info.Env(), "The object size or chunk count is invalid.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    return queue(info.Env(), Operation::Finish, info[0].As<Napi::String>().Utf8Value(),
      std::to_string(static_cast<std::size_t>(size)), info[3].As<Napi::String>().Utf8Value(),
      static_cast<std::size_t>(count));
  }

  Napi::Value GetObject(const Napi::CallbackInfo& info) {
    return queue_key(info, Operation::Get);
  }

  Napi::Value GetObjectInfo(const Napi::CallbackInfo& info) {
    return queue_key(info, Operation::Info);
  }

  Napi::Value ReadChunk(const Napi::CallbackInfo& info) {
    if (info.Length() < 2 || !info[0].IsString() || !info[1].IsNumber()) {
      Napi::TypeError::New(info.Env(), "readChunk requires (key, chunkIndex).").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const double index = info[1].As<Napi::Number>().DoubleValue();
    if (index < 0 || index > 255 || index != static_cast<double>(static_cast<std::size_t>(index))) {
      Napi::RangeError::New(info.Env(), "The chunk index is invalid.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    return queue(info.Env(), Operation::ReadChunk, info[0].As<Napi::String>().Utf8Value(), {}, {}, static_cast<std::size_t>(index));
  }

  Napi::Value DeleteObject(const Napi::CallbackInfo& info) {
    return queue_key(info, Operation::Delete);
  }

  Napi::Value CreateCheckpoint(const Napi::CallbackInfo& info) {
    if (info.Length() < 1 || !info[0].IsString()) {
      Napi::TypeError::New(info.Env(), "createCheckpoint requires a destination directory.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    const std::string path = info[0].As<Napi::String>().Utf8Value();
    if (path.empty()) {
      Napi::TypeError::New(info.Env(), "The RocksDB checkpoint path cannot be empty.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    return queue(info.Env(), Operation::Checkpoint, "checkpoint", path);
  }

  Napi::Value Close(const Napi::CallbackInfo& info) {
    database_.reset();
    return info.Env().Undefined();
  }

  Napi::Value queue_key(const Napi::CallbackInfo& info, Operation operation) {
    if (info.Length() < 1 || !info[0].IsString()) {
      Napi::TypeError::New(info.Env(), "A storage key is required.").ThrowAsJavaScriptException();
      return info.Env().Undefined();
    }
    return queue(info.Env(), operation, info[0].As<Napi::String>().Utf8Value());
  }

  Napi::Value queue(
      Napi::Env env,
      Operation operation,
      std::string key,
      std::string bytes = {},
      std::string metadata = {},
      std::size_t chunk = 0) {
    if (!database_) {
      Napi::Error::New(env, "RocksDB storage is closed.").ThrowAsJavaScriptException();
      return env.Undefined();
    }
    if (key.empty() || key.size() > 512) {
      Napi::RangeError::New(env, "Storage keys must contain 1–512 bytes.").ThrowAsJavaScriptException();
      return env.Undefined();
    }
    auto deferred = Napi::Promise::Deferred::New(env);
    auto promise = deferred.Promise();
    auto* worker = new ObjectWorker(env, std::move(deferred), database_, operation,
      std::move(key), std::move(bytes), std::move(metadata), chunk);
    worker->Queue();
    return promise;
  }

  std::shared_ptr<rocksdb::DB> database_;
  static Napi::FunctionReference constructor;
};

Napi::FunctionReference RocksStore::constructor;

Napi::Object Init(Napi::Env env, Napi::Object exports) {
#ifdef LEMEGETON_HAS_BLA_SHIELD
  (void)BLA_SHIELD_ANCHOR(0x4C454D45U);
#endif
  return RocksStore::Init(env, exports);
}

NODE_API_MODULE(NODE_GYP_MODULE_NAME, Init)
