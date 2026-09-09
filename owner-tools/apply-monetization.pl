#!/usr/bin/perl
use strict; use warnings; use JSON::PP; use File::Basename qw(dirname); use File::Temp qw(tempfile tempdir); use File::Copy qw(copy);
my ($path,$settings)=@ARGV; die "Use apply-monetization.pl CONFIG SETTINGS\n" unless @ARGV==2;
my $json=JSON::PP->new->utf8->canonical->pretty;
sub read_json { my($p)=@_; die "Not a regular settings file: $p\n" unless -f $p && !-l $p && -s $p < 200000; open my $f,'<:raw',$p or die $!; local $/; my $d=$json->decode(<$f>); die "Expected a settings object\n" unless ref($d) eq 'HASH'; return $d; }
my $current=read_json($path); my $patch=read_json($settings);
die "Choose Brief-Monetization.json\n" unless ($patch->{schema_version}//'') eq 'aieo_brief_monetization_v1';
for(keys %$patch){die "Unexpected settings field $_\n" unless /^(schema_version|adsense|support_url|sponsor)$/;}
if(exists $patch->{adsense}){
 my $a=$patch->{adsense};die "Invalid advertising settings\n" unless ref($a) eq 'HASH';
 for(keys %$a){die "Unexpected advertising setting\n" unless /^(enabled|cmp_enabled|publisher_id|mode|slots)$/;}
 for('enabled','cmp_enabled'){die "Expected true or false\n" unless JSON::PP::is_bool($a->{$_});}
 die "Invalid publisher ID\n" unless ($a->{publisher_id}//'') =~ /^ca-pub-\d{16}$/;
 die "Invalid ad mode\n" unless ($a->{mode}//'') =~ /^(auto|placements)$/;
 die "Invalid ad slots\n" unless ref($a->{slots}) eq 'HASH'; my $filled=0;
 for(keys %{$a->{slots}}){die "Invalid placement\n" unless /^(feed|rail|story)$/;my $v=$a->{slots}{$_};die "Ad-unit IDs must contain only digits\n" if ref($v)||!defined($v)||$v !~ /^(\d{1,20})?$/;$filled++ if length $v;}
 die "Publish the Google consent message before enabling ads\n" if $a->{enabled} && !$a->{cmp_enabled};
 die "Add an ad-unit ID\n" if $a->{enabled} && $a->{mode} eq 'placements' && !$filled;
 $current->{adsense}={%{$current->{adsense}//{}},%$a};
 $current->{site_url}='https://brief.hamelberg-ai.com' unless $current->{site_url};
}
if(exists $patch->{support_url}){my $u=$patch->{support_url};die "Use a complete HTTPS support link\n" if ref($u)||!defined($u)||($u ne '' && $u !~ m{^https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?\#][^\s<>]*)?$});$current->{support_url}=$u;}
if(exists $patch->{sponsor}){
 my $s=$patch->{sponsor};die "Invalid sponsor settings\n" unless ref($s) eq 'HASH' && JSON::PP::is_bool($s->{enabled});
 for(keys %$s){die "Unexpected sponsor setting\n" unless /^(enabled|name|message|url|starts|ends)$/;}
 if($s->{enabled}){
  for('name','message','url','starts','ends'){die "Sponsor details are missing\n" if ref($s->{$_})||!defined($s->{$_})||$s->{$_} eq '';}
  die "Sponsor message is too long\n" if length($s->{name})>100||length($s->{message})>180;
  die "Use a sponsor HTTPS URL\n" unless $s->{url}=~m{^https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?\#][^\s<>]*)?$};
  for('starts','ends'){die "Use YYYY-MM-DD campaign dates\n" unless $s->{$_}=~/^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;}
  for('starts','ends'){
   my($year,$month,$day)=split /-/,$s->{$_};my @days=(31,28,31,30,31,30,31,31,30,31,30,31);
   $days[1]=29 if $year%4==0 && ($year%100!=0 || $year%400==0);
   die "Campaign date does not exist\n" if $day>$days[$month-1];
  }
  die "Sponsor end precedes start\n" if $s->{ends} lt $s->{starts};
 }
 $current->{sponsor}={%{$current->{sponsor}//{}},%$s};
}
my $old=read_json($path);if($json->encode($old) eq $json->encode($current)){print "Settings already up to date.\n";exit 0;}
my $parent=dirname(dirname(dirname($path)));my $backup=tempdir('Brief-settings-backup-XXXXXX',DIR=>$parent,CLEANUP=>0);copy($path,"$backup/site.json") or die $!;
my($f,$temp)=tempfile('.brief-settings-XXXXXX',DIR=>dirname($path),UNLINK=>0);binmode $f;print $f $json->encode($current);close $f or die $!;chmod 0644,$temp;rename $temp,$path or die $!;
print "Monetization settings saved. Backup: $backup\nCommit and push aieo-brief in GitHub Desktop.\n";
