CREATE TABLE `form_xray_viewer` (
	`id` bigint(20) NOT NULL auto_increment,
	`date` datetime default NULL,
	`pid` bigint(20) NOT NULL,
	`encounter` bigint(20) NOT NULL,
	`user` varchar(255) default NULL,
	`groupname` varchar(255) default NULL,
	`authorized` tinyint(4) NOT NULL default '0',
	`activity` tinyint(4) NOT NULL default '1',
	PRIMARY KEY (`id`)
	) ENGINE=InnoDB;
