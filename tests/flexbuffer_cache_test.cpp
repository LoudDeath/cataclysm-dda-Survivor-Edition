#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>

#include "cata_catch.h"
#include "flexbuffer_cache.h"
#include "json_cache_path.h"
#include "options_helpers.h"
#include "path_info.h"

namespace
{
struct temporary_directory {
    std::filesystem::path path;

    explicit temporary_directory( const std::string &name ) : path( std::filesystem::temp_directory_path() /
            ( "cdda_" + name + "_" + std::to_string(
                  std::chrono::steady_clock::now().time_since_epoch().count() ) ) ) {
        std::filesystem::create_directories( path );
    }

    ~temporary_directory() {
        std::error_code ec;
        std::filesystem::remove_all( path, ec );
    }
};

void write_json( const std::filesystem::path &path, const std::string &contents,
                 std::filesystem::file_time_type modified )
{
    std::ofstream file( path, std::ios::binary | std::ios::trunc );
    file << contents;
    file.close();
    std::filesystem::last_write_time( path, modified );
}

int parse_integer( const std::shared_ptr<parsed_flexbuffer> &parsed )
{
    return flexbuffers::GetRoot( parsed->get_storage()->data(), parsed->get_storage()->size() ).AsInt32();
}
} // namespace

TEST_CASE( "flexbuffer_cache_reparses_changed_json_without_a_modal_error", "[flexbuffer_cache]" )
{
    override_option warn_on_modified( "WARN_ON_MODIFIED", "true" );
    temporary_directory temp( "flexbuffer_cache_upgrade" );
    const std::filesystem::path source_root = temp.path / "game";
    const std::filesystem::path cache_root = temp.path / "cache";
    std::filesystem::create_directories( source_root );
    const std::filesystem::path source = source_root / "content.json";
    const auto initial_mtime = std::filesystem::file_time_type::clock::now();
    write_json( source, "1", initial_mtime );

    {
        flexbuffer_cache cache( cache_root, source_root );
        REQUIRE( parse_integer( cache.parse_and_cache( source ) ) == 1 );
    }

    write_json( source, "2", initial_mtime + std::chrono::seconds( 2 ) );
    {
        // Reopening the cache exercises the disk index and stale-mtime path used at startup.
        flexbuffer_cache cache( cache_root, source_root );
        REQUIRE( parse_integer( cache.parse_and_cache( source ) ) == 2 );
    }

    write_json( source, "{ invalid", initial_mtime + std::chrono::seconds( 4 ) );
    // The malformed source must still fail after the stale disk entry is discarded.
    flexbuffer_cache cache( cache_root, source_root );
    REQUIRE_THROWS( cache.parse_and_cache( source ) );
}

#if defined(_WIN32)
TEST_CASE( "windows_json_cache_namespace_tracks_source_install", "[flexbuffer_cache]" )
{
    temporary_directory temp( "flexbuffer_cache_namespace" );
    const std::filesystem::path first_install = temp.path / "install-one";
    const std::filesystem::path second_install = temp.path / "install-two";

    CHECK( PATH_INFO::cache_dir( first_install ) == PATH_INFO::cache_dir( first_install ) );
    CHECK( PATH_INFO::cache_dir( first_install ) != PATH_INFO::cache_dir( second_install ) );
}
#endif
