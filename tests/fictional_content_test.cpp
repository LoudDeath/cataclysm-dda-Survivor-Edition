#include <algorithm>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#include "calendar.h"
#include "cata_catch.h"
#include "flexbuffer_json.h"
#include "item.h"
#include "item_factory.h"
#include "json_loader.h"
#include "path_info.h"
#include "recipe.h"
#include "recipe_dictionary.h"
#include "type_id.h"

namespace
{
int price_for_quantity( const std::string &id, int quantity )
{
    item value( itype_id( id ), calendar::turn_zero, item::default_charges_tag{} );
    if( value.count_by_charges() ) {
        value.charges = quantity;
        return value.price( false );
    }
    return value.price( false ) * quantity;
}
} // namespace

TEST_CASE( "fictional_reagents_keep_one_cent_per_charge_price", "[content][fictional][price]" )
{
    const std::vector<std::string> reagents = {
        "survivor_gloam_resin", "survivor_hollow_salt", "survivor_echo_solution"
    };
    for( const std::string &id : reagents ) {
        INFO( "reagent id: " << id );
        item reagent( itype_id( id ), calendar::turn_zero, item::default_charges_tag{} );
        REQUIRE( item::type_is_defined( itype_id( id ) ) );
        REQUIRE( reagent.count_by_charges() );
        CHECK_FALSE( reagent.is_comestible() );
        reagent.charges = 1;
        CHECK( reagent.price( false ) == 1 );
        reagent.charges = 100;
        CHECK( reagent.price( false ) == 100 );
        if( id == "survivor_echo_solution" ) {
            CHECK( reagent.made_of( phase_id::LIQUID ) );
        }
    }
}

TEST_CASE( "legacy_drug_item_ids_and_charges_survive_json_round_trip", "[content][fictional][save]" )
{
    const std::vector<std::string> old_ids = {
        "morphine", "codeine", "coke", "meth", "weed", "joint", "datura_seed",
        "diazepam", "prozac", "xanax", "heroin", "oxycodone", "tramadol", "aspirin"
    };
    for( const std::string &id : old_ids ) {
        INFO( "legacy item id: " << id );
        const itype_id type( id );
        REQUIRE( item::type_is_defined( type ) );
        item original( type, calendar::turn_zero );
        if( original.count_by_charges() ) {
            original.charges = 37;
        }

        std::ostringstream serialized;
        {
            JsonOut json( serialized );
            original.serialize( json );
        }
        const JsonValue saved = json_loader::from_string( serialized.str() );
        item restored;
        restored.deserialize( saved.get_object() );
        CHECK( restored.typeId() == type );
        CHECK( restored.charges == original.charges );
    }
}

TEST_CASE( "fictional_recipe_reagent_budgets_track_removed_component_value",
           "[content][fictional][recipes][price]" )
{
    const JsonValue fixture_value = json_loader::from_path(
                                       PATH_INFO::base_path() / "tests" / "data" / "fictional_recipe_baselines.json" );
    const JsonObject fixture = fixture_value.get_object();
    const JsonArray recipes = fixture.get_array( "recipes" );
    REQUIRE( recipes.size() > 0 );

    for( size_t index = 0; index < recipes.size(); ++index ) {
        const JsonObject baseline = recipes.get_object( index );
        const std::string recipe_id_text = baseline.get_string( "recipe_id" );
        INFO( "audit recipe: " << baseline.get_string( "audit_recipe_id" ) );
        const auto found = std::find_if( recipe_dict.begin(), recipe_dict.end(),
        [&recipe_id_text]( const auto &entry ) {
            return entry.first.str() == recipe_id_text;
        } );
        REQUIRE( found != recipe_dict.end() );
        const recipe &live = found->second;
        CHECK( live.result().str() == baseline.get_string( "result" ) );
        if( baseline.has_int( "baseline_difficulty" ) ) {
            CHECK( live.difficulty == baseline.get_int( "baseline_difficulty" ) );
        }
        if( baseline.has_int( "baseline_charges" ) ) {
            CHECK( live.makes_amount() == baseline.get_int( "baseline_charges" ) );
        }

        const JsonArray removed_groups = baseline.get_array( "removed_groups" );
        int removed_value = 0;
        for( size_t group_index = 0; group_index < removed_groups.size(); ++group_index ) {
            const JsonArray alternatives = removed_groups.get_array( group_index );
            REQUIRE( alternatives.size() > 0 );
            int cheapest_option = std::numeric_limits<int>::max();
            for( size_t option_index = 0; option_index < alternatives.size(); ++option_index ) {
                const JsonObject component = alternatives.get_object( option_index );
                const std::string component_id = component.get_string( "id" );
                const int count = component.get_int( "count" );
                REQUIRE( item::type_is_defined( itype_id( component_id ) ) );
                cheapest_option = std::min( cheapest_option, price_for_quantity( component_id, count ) );
            }
            removed_value += cheapest_option;
        }

        const JsonArray reagent_budgets = baseline.get_array( "reagent_budgets" );
        REQUIRE( reagent_budgets.size() > 0 );
        int new_budget = 0;
        for( size_t reagent_index = 0; reagent_index < reagent_budgets.size(); ++reagent_index ) {
            const JsonObject expected = reagent_budgets.get_object( reagent_index );
            const std::string reagent_id = expected.get_string( "id" );
            const int charges = expected.get_int( "charges" );
            REQUIRE( item::type_is_defined( itype_id( reagent_id ) ) );
            new_budget += price_for_quantity( reagent_id, charges );

            bool found_requirement = false;
            for( const std::vector<item_comp> &group : live.simple_requirements().get_components() ) {
                for( const item_comp &component : group ) {
                    if( component.type == itype_id( reagent_id ) && component.count == charges ) {
                        found_requirement = true;
                    }
                }
            }
            CHECK( found_requirement );
        }
        REQUIRE( removed_value > 0 );
        INFO( "old removed components: " << removed_value << " cents; new reagent budget: " << new_budget << " cents" );
        CHECK( new_budget * 10 >= removed_value * 9 );
        CHECK( new_budget * 10 <= removed_value * 11 );
    }
}
