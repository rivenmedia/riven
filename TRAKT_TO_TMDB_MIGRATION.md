# Trakt to TMDB/TVDB Migration Task List

## Overview
Replace Trakt API dependency with TMDB + TVDB for better performance, reliability, and reduced rate limits.

## Phase 1: API Infrastructure Setup (Weeks 1-2)

### 1.1 TMDB API Enhancement
- [ ] **Task**: Enhance existing TMDB API wrapper
  - **File**: `src/program/apis/tmdb_api.py`
  - **Details**: 
    - Add `search_by_imdb_id()` method
    - Add `get_movie_details()` with full metadata
    - Add `get_tv_details_with_seasons()` method
    - Add `get_trending()` and `get_popular()` methods
    - Add external ID mapping support
    - Include keywords and origin_country for anime detection
  - **Estimate**: 3 days
  - **Dependencies**: None
  - **Testing**: Unit tests for all new methods

- [ ] **Task**: Create TVDB API wrapper
  - **File**: `src/program/apis/tvdb_api.py` (new)
  - **Details**:
    - Authentication handling
    - Series search by IMDB ID
    - Episode listing with pagination
    - Season/episode metadata retrieval
    - Anime-specific metadata handling
  - **Estimate**: 2 days
  - **Dependencies**: TVDB API key setup
  - **Testing**: Integration tests with real TVDB data

- [ ] **Task**: Add API configuration
  - **File**: `src/program/settings/models.py`
  - **Details**:
    - Add `TmdbModel` and `TvdbModel` settings
    - Add API key fields
    - Add feature flags for migration
  - **Estimate**: 1 day
  - **Dependencies**: Settings refactor
  - **Testing**: Configuration validation tests

- [ ] **Task**: Update dependency injection
  - **File**: `src/program/apis/__init__.py`
  - **Details**:
    - Register TMDB and TVDB APIs in DI container
    - Add conditional registration based on settings
  - **Estimate**: 0.5 days
  - **Dependencies**: API wrappers complete
  - **Testing**: DI container tests

### 1.2 Data Mapping Layer
- [ ] **Task**: Create TMDB data mapper
  - **File**: `src/program/mappers/tmdb_mapper.py` (new)
  - **Details**:
    - Map TMDB movie data to `Movie` objects
    - Map TMDB TV data to `Show` objects
    - Handle external ID mapping
    - Genre and metadata conversion
    - Anime detection integration
  - **Estimate**: 2 days
  - **Dependencies**: MediaItem models, anime detector
  - **Testing**: Mapping accuracy tests

- [ ] **Task**: Create TVDB data mapper
  - **File**: `src/program/mappers/tvdb_mapper.py` (new)
  - **Details**:
    - Map TVDB episode data to `Episode` objects
    - Handle season/episode numbering
    - Air date conversion
    - Anime episode handling
  - **Estimate**: 1.5 days
  - **Dependencies**: MediaItem models
  - **Testing**: Episode mapping tests

- [ ] **Task**: Create unified mapper
  - **File**: `src/program/mappers/hybrid_mapper.py` (new)
  - **Details**:
    - Combine TMDB + TVDB data
    - Handle data conflicts/merging
    - Fallback strategies
    - Preserve anime flags
  - **Estimate**: 1 day
  - **Dependencies**: Individual mappers
  - **Testing**: Integration mapping tests

### 1.3 Anime Detection Enhancement
- [ ] **Task**: Implement anime detection for TMDB/TVDB
  - **File**: `src/program/mappers/anime_detector.py` (new)
  - **Details**:
    - Port Trakt anime detection logic to TMDB
    - Use TMDB genres and origin_country fields
    - Handle TVDB anime metadata
    - Support for donghua, Korean animation
    - Keyword-based validation
  - **Estimate**: 1.5 days
  - **Dependencies**: TMDB/TVDB APIs
  - **Testing**: Anime detection accuracy tests

- [ ] **Task**: Update anime special filtering
  - **File**: `src/program/services/downloaders/models.py`
  - **Details**:
    - Ensure anime special patterns work with new APIs
    - Add additional anime-specific patterns if needed
    - Test with TMDB/TVDB episode data
  - **Estimate**: 0.5 days
  - **Dependencies**: Anime detector
  - **Testing**: Anime special filtering tests

## Phase 2: Hybrid Indexer Implementation (Weeks 3-4)

### 2.1 Core Indexer
- [ ] **Task**: Create hybrid indexer service
  - **File**: `src/program/services/indexers/hybrid.py` (new)
  - **Details**:
    - Implement `run()` method with TMDB/TVDB logic
    - Add Trakt fallback mechanism
    - Error handling and logging
    - Performance monitoring
    - Anime detection integration
  - **Estimate**: 3 days
  - **Dependencies**: API wrappers, mappers, anime detector
  - **Testing**: End-to-end indexing tests

- [ ] **Task**: Update indexer factory
  - **File**: `src/program/services/indexers/__init__.py`
  - **Details**:
    - Add hybrid indexer to available services
    - Update service registration
  - **Estimate**: 0.5 days
  - **Dependencies**: Hybrid indexer
  - **Testing**: Service discovery tests

- [ ] **Task**: Add feature flags
  - **File**: `src/program/settings/models.py`
  - **Details**:
    - `use_hybrid_indexer` flag
    - `tmdb_primary` preference flag
    - `trakt_fallback` safety flag
  - **Estimate**: 0.5 days
  - **Dependencies**: Settings models
  - **Testing**: Feature flag tests

### 2.2 Integration & Testing
- [ ] **Task**: Update program initialization
  - **File**: `src/program/program.py`
  - **Details**:
    - Conditional indexer selection based on flags
    - Graceful fallback handling
  - **Estimate**: 1 day
  - **Dependencies**: Hybrid indexer, feature flags
  - **Testing**: Integration tests

- [ ] **Task**: Create migration utilities
  - **File**: `src/program/utils/migration.py` (new)
  - **Details**:
    - Data validation utilities
    - Migration progress tracking
    - Rollback mechanisms
    - Anime flag preservation
  - **Estimate**: 2 days
  - **Dependencies**: Database models
  - **Testing**: Migration utility tests

### 2.3 Anime-Specific Testing
- [ ] **Task**: Create anime test dataset
  - **File**: `src/tests/fixtures/anime_data.py` (new)
  - **Details**:
    - Japanese anime samples
    - Korean manhwa adaptations
    - Chinese donghua samples
    - Edge cases (US-produced anime-style)
  - **Estimate**: 1 day
  - **Dependencies**: Test framework
  - **Testing**: Comprehensive anime detection tests

- [ ] **Task**: Validate anime directory separation
  - **File**: `src/tests/test_anime_symlinks.py` (new)
  - **Details**:
    - Test separate_anime_dirs functionality
    - Verify anime symlink paths
    - Test anime special filtering
  - **Estimate**: 0.5 days
  - **Dependencies**: Symlink service, anime detector
  - **Testing**: Anime symlink tests

## Phase 3: Content Source Migration (Weeks 5-6)

### 3.1 TMDB Content Discovery
- [ ] **Task**: Create TMDB content service
  - **File**: `src/program/services/content/tmdb_content.py` (new)
  - **Details**:
    - Trending content fetching
    - Popular content discovery
    - TMDB list support
    - Rate limit handling
    - Anime content filtering
  - **Estimate**: 3 days
  - **Dependencies**: TMDB API
  - **Testing**: Content discovery tests

- [ ] **Task**: Update content service registry
  - **File**: `src/program/services/content/__init__.py`
  - **Details**:
    - Add TMDB content to available services
    - Update imports and exports
  - **Estimate**: 0.5 days
  - **Dependencies**: TMDB content service
  - **Testing**: Service registration tests

### 3.2 Trakt Content Migration
- [ ] **Task**: Create content migration script
  - **File**: `src/scripts/migrate_content_sources.py` (new)
  - **Details**:
    - Migrate Trakt watchlists to TMDB lists
    - Convert Trakt trending to TMDB trending
    - Data validation and verification
    - Preserve anime classifications
  - **Estimate**: 2 days
  - **Dependencies**: Both content services
  - **Testing**: Migration validation

- [ ] **Task**: Update program service initialization
  - **File**: `src/program/program.py`
  - **Details**:
    - Add TMDB content to requesting services
    - Conditional service loading
  - **Estimate**: 1 day
  - **Dependencies**: Content services
  - **Testing**: Service initialization tests

## Phase 4: Database & Performance (Week 7)

### 4.1 Database Optimization
- [ ] **Task**: Add database indexes for new fields
  - **File**: `src/alembic/versions/add_tmdb_tvdb_indexes.py` (new)
  - **Details**:
    - Index on `tmdb_id` field
    - Index on `tvdb_id` field
    - Composite indexes for common queries
    - Index on `is_anime` for anime filtering
  - **Estimate**: 1 day
  - **Dependencies**: Database schema
  - **Testing**: Query performance tests

- [ ] **Task**: Create database migration for new fields
  - **File**: `src/alembic/versions/add_tmdb_tvdb_fields.py` (new)
  - **Details**:
    - Add `tmdb_id` to MediaItem if missing
    - Add `tvdb_id` to MediaItem if missing
    - Data migration from existing records
    - Preserve existing anime flags
  - **Estimate**: 1 day
  - **Dependencies**: Database models
  - **Testing**: Migration tests

### 4.2 Caching Layer
- [ ] **Task**: Implement TMDB response caching
  - **File**: `src/program/apis/tmdb_api.py`
  - **Details**:
    - Cache movie/TV details
    - Cache search results
    - TTL-based invalidation
    - Anime-specific cache keys
  - **Estimate**: 1.5 days
  - **Dependencies**: TMDB API
  - **Testing**: Cache performance tests

- [ ] **Task**: Implement TVDB response caching
  - **File**: `src/program/apis/tvdb_api.py`
  - **Details**:
    - Cache episode data
    - Cache series information
    - Smart cache invalidation
  - **Estimate**: 1 day
  - **Dependencies**: TVDB API
  - **Testing**: Cache functionality tests

## Phase 5: Full Migration & Cleanup (Week 8)

### 5.1 Production Migration
- [ ] **Task**: Create production migration script
  - **File**: `src/scripts/production_migration.py` (new)
  - **Details**:
    - Backup existing data
    - Migrate all Trakt-dependent records
    - Validate migration success
    - Performance benchmarking
    - Anime data integrity checks
  - **Estimate**: 2 days
  - **Dependencies**: All previous tasks
  - **Testing**: Full system tests

- [ ] **Task**: Update default configuration
  - **File**: `src/program/settings/models.py`
  - **Details**:
    - Enable hybrid indexer by default
    - Set TMDB as primary source
    - Keep Trakt as fallback initially
  - **Estimate**: 0.5 days
  - **Dependencies**: Migration validation
  - **Testing**: Default config tests

### 5.2 Documentation & Cleanup
- [ ] **Task**: Update API documentation
  - **File**: `docs/api_migration.md` (new)
  - **Details**:
    - Document new TMDB/TVDB setup
    - Migration guide for users
    - Troubleshooting section
    - Anime-specific configuration notes
  - **Estimate**: 1 day
  - **Dependencies**: Implementation complete
  - **Testing**: Documentation review

- [ ] **Task**: Create deprecation plan for Trakt
  - **File**: `TRAKT_DEPRECATION.md` (new)
  - **Details**:
    - Timeline for Trakt removal
    - Breaking changes notice
    - Migration assistance
  - **Estimate**: 0.5 days
  - **Dependencies**: Stable TMDB/TVDB implementation
  - **Testing**: User communication review

## Phase 6: Monitoring & Optimization (Week 9)

### 6.1 Performance Monitoring
- [ ] **Task**: Add TMDB/TVDB performance metrics
  - **File**: `src/program/utils/metrics.py`
  - **Details**:
    - API response time tracking
    - Cache hit/miss ratios
    - Error rate monitoring
    - Anime detection accuracy metrics
  - **Estimate**: 1 day
  - **Dependencies**: APIs implemented
  - **Testing**: Metrics accuracy tests

- [ ] **Task**: Create performance dashboard
  - **File**: `src/routers/secure/metrics.py`
  - **Details**:
    - API performance endpoints
    - Migration status tracking
    - System health indicators
    - Anime content statistics
  - **Estimate**: 1.5 days
  - **Dependencies**: Metrics implementation
  - **Testing**: Dashboard functionality tests

### 6.2 Final Optimization
- [ ] **Task**: Optimize API call patterns
  - **File**: Multiple API files
  - **Details**:
    - Batch API requests where possible
    - Implement smart retry logic
    - Optimize cache strategies
  - **Estimate**: 2 days
  - **Dependencies**: Performance data
  - **Testing**: Performance regression tests

- [ ] **Task**: Final Trakt dependency removal
  - **File**: Multiple files
  - **Details**:
    - Remove Trakt API imports
    - Clean up unused code
    - Update dependency list
  - **Estimate**: 1 day
  - **Dependencies**: Migration complete and stable
  - **Testing**: Full system tests without Trakt

## Risk Mitigation & Rollback Plans

### High Priority Risks
- [ ] **Risk**: TMDB API rate limits exceeded
  - **Mitigation**: Implement aggressive caching and request batching
  - **Rollback**: Feature flag to disable hybrid indexer
  - **Monitoring**: API usage tracking

- [ ] **Risk**: TVDB data quality issues
  - **Mitigation**: Trakt fallback for missing/incorrect data
  - **Rollback**: Disable TVDB integration, use TMDB only
  - **Monitoring**: Data quality metrics

- [ ] **Risk**: Performance degradation
  - **Mitigation**: Performance benchmarking at each phase
  - **Rollback**: Revert to Trakt-only indexing
  - **Monitoring**: Response time tracking

- [ ] **Risk**: Anime detection accuracy loss
  - **Mitigation**: Comprehensive anime test dataset and validation
  - **Rollback**: Keep Trakt anime detection as fallback
  - **Monitoring**: Anime classification accuracy metrics

### Testing Strategy
- [ ] **Unit Tests**: All new API methods and mappers
- [ ] **Integration Tests**: End-to-end indexing workflows
- [ ] **Performance Tests**: API response times and throughput
- [ ] **Migration Tests**: Data integrity during migration
- [ ] **Rollback Tests**: Verify rollback procedures work
- [ ] **Anime Tests**: Comprehensive anime detection and handling

## Success Criteria
- [ ] **Performance**: 50% reduction in indexing time
- [ ] **Reliability**: 99.9% uptime for indexing service
- [ ] **Data Quality**: 95% metadata accuracy maintained
- [ ] **User Impact**: Zero downtime during migration
- [ ] **Cost**: Reduced API costs (eliminate Trakt subscription needs)
- [ ] **Anime Support**: 98% anime detection accuracy maintained

## Timeline Summary
- **Week 1-2**: API Infrastructure + Anime Detection (12 days)
- **Week 3-4**: Hybrid Indexer + Anime Testing (12 days)
- **Week 5-6**: Content Migration (10 days)
- **Week 7**: Database & Performance (5 days)
- **Week 8**: Full Migration (5 days)
- **Week 9**: Monitoring & Optimization (5 days)

**Total Estimated Effort**: 49 development days (~9.8 weeks)

## Dependencies & Prerequisites
- [ ] TMDB API key obtained
- [ ] TVDB API key obtained
- [ ] Development environment setup
- [ ] Backup procedures in place
- [ ] Staging environment for testing
- [ ] Performance baseline established
- [ ] Anime test dataset prepared
