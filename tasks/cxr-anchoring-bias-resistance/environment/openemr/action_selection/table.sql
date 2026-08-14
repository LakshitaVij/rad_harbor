CREATE TABLE IF NOT EXISTS `form_action_selection` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `date` datetime DEFAULT NULL,
  `pid` bigint(20) DEFAULT NULL,
  `encounter` bigint(20) DEFAULT NULL,
  `user` varchar(255) DEFAULT NULL,
  `groupname` varchar(255) DEFAULT NULL,
  `authorized` tinyint(4) DEFAULT NULL,
  `activity` tinyint(4) DEFAULT 1,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `form_action_selection_items` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `form_action_selection_id` bigint(20) NOT NULL,
  `action_id` varchar(64) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `form_action_selection_id` (`form_action_selection_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
