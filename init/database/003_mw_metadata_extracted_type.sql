-- Migration: add extracted_type to mw_metadata

ALTER TABLE `mw_metadata`
    ADD COLUMN IF NOT EXISTS `extracted_type` VARCHAR(64) NOT NULL DEFAULT 'other' AFTER `extracted_code`;

ALTER TABLE `mw_metadata`
    ADD INDEX IF NOT EXISTS `idx_extracted_type` (`extracted_type`);
