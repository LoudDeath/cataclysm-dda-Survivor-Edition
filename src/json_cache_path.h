#pragma once
#ifndef CATA_SRC_JSON_CACHE_PATH_H
#define CATA_SRC_JSON_CACHE_PATH_H

#include <filesystem>

namespace PATH_INFO
{
// Persistent cache for this source tree and compiled parser/edition version.
std::filesystem::path cache_dir( const std::filesystem::path &source_root );
} // namespace PATH_INFO

#endif
