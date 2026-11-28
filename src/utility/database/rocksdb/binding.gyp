{
  "targets": [
    {
      "target_name": "lemegeton_rocksdb",
      "sources": ["addon.cpp"],
      "include_dirs": ["<!@(node -p \"require('node-addon-api').include\")"],
      "libraries": ["-lrocksdb"],
      "defines": ["NAPI_CPP_EXCEPTIONS"],
      "cflags_cc!": ["-fno-exceptions"],
      "conditions": [
        ["OS=='win'", {
          "libraries": ["rocksdb.lib"]
        }]
      ]
    }
  ]
}
