-- Schema: mw_raw_content
-- Stores raw email content crawled from MailDev

CREATE TABLE IF NOT EXISTS `mw_raw_content` (
    `id`         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `mailid`     VARCHAR(255) NOT NULL DEFAULT '',
    `raw_header` LONGTEXT,
    `raw_body`   LONGTEXT,
    PRIMARY KEY (`id`),
    INDEX `idx_mailid` (`mailid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
