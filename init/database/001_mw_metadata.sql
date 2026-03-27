-- Schema: mw_metadata
-- Stores email metadata crawled from MailDev

CREATE TABLE IF NOT EXISTS `mw_metadata` (
    `id`                INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    `mailid`            VARCHAR(255)    NOT NULL DEFAULT '',
    `from`              VARCHAR(500)    NOT NULL DEFAULT '',
    `to`                VARCHAR(500)    NOT NULL DEFAULT '',
    `timestamp`         DATETIME        NOT NULL,
    `subject`           TEXT,
    `raw_file`          VARCHAR(1024),
    `extracted_code`    VARCHAR(255),
    `extracted_type`    VARCHAR(64)    NOT NULL DEFAULT 'other',
    `extracted_content` TEXT,
    PRIMARY KEY (`id`),
    INDEX `idx_mailid`    (`mailid`),
    INDEX `idx_from`      (`from`(255)),
    INDEX `idx_to`        (`to`(255)),
    INDEX `idx_extracted_type` (`extracted_type`),
    INDEX `idx_timestamp` (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
